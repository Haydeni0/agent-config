#!/usr/bin/env bash
# Build a critic's spawn prompt from a template, then launch a fresh critic via
# spawn-member.sh (role: critic).
# Usage: spawn-critic.sh <template> <verdict-path> <name> [--prior <previous verdict>] -- <key=path> ...
# <template> is a file in ../templates/ (with or without .md), or a path to one.
# Each <key=path> fills the template's {key}. D17: the prompt is template + paths
# only - every value must be an existing path (comma-separated lists allowed), except:
#   - the verdict path (argument 2), which must NOT exist yet (the critic writes it);
#   - keys ending in _sha, which must resolve as a commit in the repo of one of the
#     other values (the code repo).
# The finished prompt is written next to the verdict as <verdict-stem>-spawn.md,
# and the caller's ring-back line is appended so the critic reports the verdict.
# Round 2+: --prior <previous verdict> adds the re-check-prior-findings line.
# Prints the spawn prompt path, then the critic's pane id.
set -euo pipefail

fail() { echo "spawn-critic: $*" >&2; exit 1; }
here=$(cd "$(dirname "$0")" && pwd)

(($# >= 3)) || fail "usage: spawn-critic.sh <template> <verdict-path> <name> [--prior <verdict>] -- <key=path> ..."
template_arg=$1 verdict=$2 name=$3
shift 3
prior= pairs=() saw_dash=no
while (($# > 0)); do
  case $1 in
    --prior) prior=$2; shift 2 ;;
    --) saw_dash=yes; shift; pairs=("$@"); break ;;
    *) fail "unexpected argument '$1' (want --prior <verdict> or -- before the key=path pairs)" ;;
  esac
done
[[ $saw_dash == yes ]] || fail "no '--' before the key=path pairs"

template=
if [[ -f $template_arg ]]; then
  template=$template_arg
else
  for t in "$here/../templates/$template_arg" "$here/../templates/$template_arg.md"; do
    if [[ -f $t ]]; then template=$t; break; fi
  done
fi
[[ -n $template ]] || fail "template '$template_arg' not found in $here/../templates/ (pass a name or a path)"
if [[ -f $verdict ]]; then fail "verdict $verdict already exists (the critic writes it; move it or pick a new path)"; fi
verdict_dir=$(dirname "$verdict")
[[ -d $verdict_dir ]] || fail "verdict directory $verdict_dir does not exist"
if [[ -n $prior && ! -f $prior ]]; then fail "--prior verdict $prior does not exist"; fi

# the prompt is the template's ```text block, nothing else
prompt=$(sed -n '/^```text$/,/^```$/p' "$template" | sed '1d;$d')
[[ -n $prompt ]] || fail "no \`\`\`text prompt block in $template"

caller_pane=${HERDR_PANE_ID:-$(herdr pane current 2>/dev/null | jq -r '.result.pane.pane_id // empty' || true)}
[[ $caller_pane == *:p* ]] || fail "cannot tell the caller's pane (HERDR_PANE_ID unset; herdr pane current said '${caller_pane:-}')"

# one trimmed value per line for a comma-separated path list
list_paths() { tr ',' '\n' <<<"$1" | sed 's/^ *//;s/ *$//' | sed '/^$/d'; }

# every value must be an existing path; collect them so _sha keys can find a repo
# (the verdict path itself is filled from argument 2 and must NOT exist yet)
declare -A value_of
value_of[verdict_path]=$verdict
path_values=()
for pair in ${pairs[@]+"${pairs[@]}"}; do
  key=${pair%%=*} value=${pair#*=}
  [[ $pair == *=* && $key =~ ^[a-z_]+$ ]] || fail "bad pair '$pair' (want key=path, key lowercase/underscore)"
  [[ $key != verdict_path ]] || fail "verdict_path is argument 2, not a key=path pair"
  [[ -z ${value_of[$key]:-} ]] || fail "key $key given twice"
  [[ -n $value ]] || fail "empty value for $key"
  if [[ $key == *_sha ]]; then
    value_of[$key]=$value
  else
    while IFS= read -r p; do
      [[ -e $p ]] || fail "value of $key is not an existing path: $p"
      path_values+=("$p")
    done < <(list_paths "$value")
    value_of[$key]=$value
  fi
done

# _sha values must be commits in the repo of one of the given paths
repo_of_paths() {
  for p in ${path_values[@]+"${path_values[@]}"}; do
    d=$p; [[ -d $d ]] || d=${d%/*}
    top=$(git -C "$d" rev-parse --show-toplevel 2>/dev/null || true)
    if [[ -n $top ]]; then echo "$top"; return; fi
  done
  return 1
}
for key in "${!value_of[@]}"; do
  [[ $key == *_sha ]] || continue
  repo=$(repo_of_paths) || fail "cannot verify $key: none of the given paths is inside a git repo"
  git -C "$repo" rev-parse --verify --quiet "${value_of[$key]}^{commit}" >/dev/null \
    || fail "value of $key is not a commit in $repo: ${value_of[$key]} (commit the code first, or fill {exp_sha} with a real sha - no prose)"
done

for key in "${!value_of[@]}"; do
  prompt=${prompt//\{$key\}/${value_of[$key]}}
done
left=$(grep -oE '\{[a-z_]+\}' <<<"$prompt" | sort -u | tr -d '{}' | tr '\n' ' ' || true)
[[ -z $left ]] || fail "template keys not filled: $left"

spawn_file=$verdict-spawn.md
if [[ $verdict == *.* ]]; then spawn_file=${verdict%.*}-spawn.md; fi
{
  printf '%s\n' "$prompt"
  if [[ -n $prior ]]; then
    printf '\nPrior round verdict: %s. Re-check its findings first - confirm or retract\neach against the data - then audit afresh; do not stop at the prior round.\n' "$prior"
  fi
  printf '\nWhen the verdict file is written, ring the caller with exactly this line:\nherdr agent prompt %s "done: %s"\n' "$caller_pane" "$verdict"
} > "$spawn_file"

# the critic reads files by absolute path; give it the lab's repo root when the
# verdict lives in one, else the verdict's directory
cwd=$(git -C "$verdict_dir" rev-parse --show-toplevel 2>/dev/null || echo "$verdict_dir")
echo "$spawn_file"
"$here/spawn-member.sh" "$name" "$cwd" "$spawn_file" critic
