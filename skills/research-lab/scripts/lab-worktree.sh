#!/usr/bin/env bash
# Create (or reuse) the lab's code worktree and record it in the lab's policy.md.
# Usage: lab-worktree.sh <lab-dir> <repo> <slug> [--setup "<cmd>"]
# Branch = <BRANCH_PREFIX>lab-<slug>, BRANCH_PREFIX from the PI profile (required).
# The worktree is made with `wt -C <repo> switch -c <branch> --no-cd`; an existing
# branch/worktree is reused, never forced. Setup belongs to the repo, in this order:
#   1. repo worktrunk project hooks (hook entries in <repo>/.config/wt.toml) - wt
#      switch already ran them, nothing to run here;
#   2. the --setup command (the overseer took it from the repo's own docs);
#   3. the profile Resources line `- Setup <repo-name>: <cmd>`.
# A command source runs in the worktree; failure fails loud with its output tail.
# None of the three = fail. A --setup command the profile does not know yet is
# appended to its Resources section with the lab and date. policy.md gets
# `Code repo:` / `Branch:` / `Worktree:` / `Setup:` lines (created when absent,
# replaced when present; lab_heartbeat.py parses the first two). Prints the
# worktree path on stdout (last line); everything else goes to stderr.
set -euo pipefail
profile=${RESEARCH_LAB_PROFILE:-$HOME/.config/research-lab/pi-profile.md}

fail() { echo "lab-worktree: $*" >&2; exit 1; }
note() { echo "lab-worktree: $*" >&2; }

usage='usage: lab-worktree.sh <lab-dir> <repo> <slug> [--setup "<cmd>"]'
lab= repo= slug= setup=
while (($#)); do
  case $1 in
    --setup) shift; [[ -n ${1:-} ]] || fail "--setup needs a command; $usage"; setup=$1 ;;
    --*) fail "unknown option $1; $usage" ;;
    *)
      if [[ -z $lab ]]; then lab=$1
      elif [[ -z $repo ]]; then repo=$1
      elif [[ -z $slug ]]; then slug=$1
      else fail "unexpected argument '$1'; $usage"
      fi ;;
  esac
  shift
done
[[ -n $lab && -n $repo && -n $slug ]] || fail "$usage"
[[ -r $profile ]] || fail "PI profile $profile unreadable - set RESEARCH_LAB_PROFILE"
repo=${repo/#\~/$HOME}
lab=${lab/#\~/$HOME}
[[ -d $repo ]] || fail "repo $repo not found"
repo=$(cd "$repo" && pwd)
lab=$(realpath -m "$lab")

prefix=$(sed -n 's/^BRANCH_PREFIX: *//p' "$profile" | head -1)
[[ -n $prefix ]] || fail "no BRANCH_PREFIX: line in $profile - cannot name the lab branch"
branch=${prefix%/}/lab-$slug

# ---- worktree: create, or reuse an existing one (never force) ----
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
err=$tmp/switch.err
if out=$(wt -C "$repo" switch -c "$branch" --no-cd --format json 2>"$err"); then
  note "created worktree for $branch"
else
  if grep -q "already exists" "$err"; then
    out=$(wt -C "$repo" switch "$branch" --no-cd --format json 2>>"$err") \
      || fail "wt switch to existing $branch in $repo failed: $(cat "$err")"
    note "branch $branch already has a worktree; reusing it"
  else
    fail "wt switch -c $branch in $repo failed: $(cat "$err")"
  fi
fi
worktree=$(jq -r '.path // empty' <<<"$out")
if [[ -z $worktree ]]; then
  # a wt too old for `switch --format json`: the path is still in wt list
  worktree=$(wt -C "$repo" list --format json 2>/dev/null \
    | jq -r --arg b "$branch" '.items[] | select(.branch == $b) | .worktree.path // empty' \
    | head -1)
fi
[[ -n $worktree ]] || fail "no worktree path from wt for $branch in $repo"
worktree=${worktree/#\~/$HOME}
[[ -d $worktree ]] || fail "wt reported worktree $worktree but it does not exist"

# ---- setup: repo hooks, else --setup, else the profile's Resources line ----
repo_name=${repo##*/}
hooks_file=$repo/.config/wt.toml
setup_source= setup_value=
if [[ -f $hooks_file ]] && rg -q \
  '^[[:space:]]*(\[\[?(pre|post)-(switch|start|commit|merge|remove)\]?]|(pre|post)-(switch|start|commit|merge|remove)[[:space:]]*=)' \
  "$hooks_file"; then
  setup_source=hooks
  setup_value="repo wt hooks"
  note "$repo_name has worktrunk project hooks; wt switch already ran them"
elif [[ -n $setup ]]; then
  setup_source=cli
  setup_value=$setup
else
  profile_setup=$(awk -v rn="$repo_name" '
    /^## Resources/ { on = 1; next }
    /^## / { on = 0 }
    on && index($0, "- Setup " rn ": ") == 1 {
      s = substr($0, length("- Setup " rn ": ") + 1)
      sub(/ \(verified:.*\)$/, "", s)  # a prior lab verification note is not part of the command
      print s; exit
    }' "$profile")
  if [[ -n $profile_setup ]]; then
    setup_source=profile
    setup_value=$profile_setup
  fi
fi
[[ -n $setup_source ]] || fail "no setup source for $repo_name: no worktrunk project hooks \
in $hooks_file, no --setup given, no '- Setup $repo_name:' line under Resources in $profile"
if [[ $setup_source != hooks ]]; then
  rc=0
  (cd "$worktree" && bash -c "$setup_value") >"$tmp/setup.out" 2>&1 || rc=$?
  if ((rc != 0)); then
    fail "setup command failed (exit $rc) in $worktree: $setup_value
last output:
$(tail -n 20 "$tmp/setup.out")"
  fi
fi

# ---- record in policy.md (replace in place, else append) ----
mkdir -p "$lab"
policy=$lab/policy.md
[[ -f $policy ]] || : >"$policy"
set_policy_line() { # $1 = key, $2 = value; first `Key:` line replaced, dups dropped
  local key=$1 value=$2 found=no line new=$tmp/policy.new
  : >"$new"
  while IFS= read -r line || [[ -n $line ]]; do
    if [[ $line =~ ^[[:space:]]*[-*]?[[:space:]]*${key}:[[:space:]] ]]; then
      [[ $found == no ]] && printf '%s: %s\n' "$key" "$value" >>"$new"
      found=yes
    else
      printf '%s\n' "$line" >>"$new"
    fi
  done <"$policy"
  [[ $found == yes ]] || printf '%s: %s\n' "$key" "$value" >>"$new"
  mv "$new" "$policy"
}
set_policy_line "Code repo" "$repo"
set_policy_line "Branch" "$branch"
set_policy_line "Worktree" "$worktree"
set_policy_line "Setup" "$setup_value"

# ---- a --setup the profile does not know yet becomes a Resources entry ----
if [[ $setup_source == cli ]] && ! awk -v rn="$repo_name" '
    /^## Resources/ { on = 1; next } /^## / { on = 0 }
    on && index($0, "- Setup " rn ": ") == 1 { found = 1; exit }
    END { exit found ? 0 : 1 }' "$profile"; then
  entry="- Setup $repo_name: $setup (verified: lab $slug, $(date +%Y-%m-%d))"
  if grep -q '^## Resources' "$profile"; then
    awk -v e="$entry" '
      /^## Resources/ { ins = 1; print; next }
      ins && /^## / { print e; ins = 0 }
      { print }
      END { if (ins) print e }' "$profile" >"$tmp/profile.new"
    mv "$tmp/profile.new" "$profile"
  else
    printf '\n## Resources\n%s\n' "$entry" >>"$profile"
  fi
  note "appended to $profile: $entry"
fi

echo "$worktree"
