#!/usr/bin/env bash
# Tear down research-lab members: close their herdr tabs, remove their mailbox member
# files, and (whole-lab mode) remove lab worktrees that are safe to drop.
# Usage: lab-teardown.sh [--apply] <lab-dir> [member ...]
#   no members: every member in <lab>/mailbox/members, and worktree cleanup runs;
#   members given: only their tabs and member files (worktree cleanup is lab-scoped,
#   so it runs only when the whole lab is torn down).
# Worktree state (dirty, ahead of main, merged) comes from `wt -C <repo> list --format
# json`; removal is `wt -C <repo> remove --foreground <branch>`, which deletes the
# branch only when merged - unmerged lab branches (the provenance records) survive by
# design; never pass -D. Dirty worktrees are reported, never removed. A worktree is
# lab-scoped when its branch or path is named in the lab's files.
# Dry-run by default; --apply acts. The caller's own pane and role=PI members are
# never closed; close your own tab after the final report.
set -euo pipefail

fail() { echo "lab-teardown: $*" >&2; exit 1; }
say() { echo "lab-teardown: $*"; }

apply=no
if [[ ${1:-} == --apply ]]; then apply=yes; shift; fi
(($# >= 1)) || fail "usage: lab-teardown.sh [--apply] <lab-dir> [member ...]"
lab=$1
shift
[[ -d $lab ]] || fail "lab dir $lab not found"
lab=$(cd "$lab" && pwd)
members_dir=$lab/mailbox/members
[[ -d $members_dir ]] || fail "no $members_dir (not a lab dir, or the mesh was never set up?)"

if (($# == 0)); then
  whole_lab=yes
  shopt -s nullglob
  member_files=("$members_dir"/*)
  shopt -u nullglob
  ((${#member_files[@]} > 0)) || fail "no member files in $members_dir"
else
  whole_lab=no
  member_files=()
  for m in "$@"; do
    mf=$members_dir/${m##*/}
    [[ -f $mf ]] || fail "no member file for '$m' in $members_dir"
    member_files+=("$mf")
  done
fi

caller_pane=${HERDR_PANE_ID:-$(herdr pane current 2>/dev/null | jq -r '.result.pane.pane_id // empty' || true)}

for mf in "${member_files[@]}"; do
  name=${mf##*/}
  role=$(sed -n 's/^role=//p' "$mf" | head -1)
  if [[ $role == PI* ]]; then
    say "$name: kept (role=PI; the PI closes their own pane)"
    continue
  fi
  pane=$(sed -n 's/^pane=//p' "$mf" | head -1)
  if [[ -n $pane && $pane == "${caller_pane:-}" ]]; then
    say "$name: kept (pane $pane is the caller's own; close your tab after the final report)"
    continue
  fi
  if [[ -z $pane ]]; then
    say "$name: no pane= in its member file (seat-less); no tab to close"
  else
    tab=$(herdr agent get "$pane" 2>/dev/null | jq -r '.result.agent.tab_id // empty' || true)
    if [[ -z $tab ]]; then
      say "$name: no live agent at $pane; close its tab by hand if one is left"
    elif [[ $apply == yes ]]; then
      herdr tab close "$tab" >/dev/null || fail "herdr tab close $tab (member $name) failed"
      say "$name: closed tab $tab (pane $pane)"
    else
      say "[dry-run] $name: would close tab $tab (pane $pane)"
    fi
  fi
  if [[ $apply == yes ]]; then
    rm "$mf"
    say "$name: removed member file"
  else
    say "[dry-run] $name: would remove member file"
  fi
done

if [[ $whole_lab != yes ]]; then
  say "member subset given: worktree cleanup skipped (it is lab-scoped)"
  exit 0
fi

# ---- whole lab: worktrees named by the lab's own files ----
shopt -s nullglob globstar
lab_files=("$lab"/*.md "$lab"/**/*.md "$lab"/*.py "$lab"/**/*.py)
shopt -u nullglob globstar
((${#lab_files[@]} > 0)) || fail "no .md/.py files under $lab to read worktree names from"
lab_text=$(cat "${lab_files[@]}")
[[ -n $lab_text ]] || fail "no text under $lab to read worktree names from"

# repos named by paths in the lab's files (~/... expanded)
repos=$(while IFS= read -r p; do
  p=${p/#\~/$HOME}
  if [[ ! -e $p ]]; then continue; fi
  d=$p; if [[ ! -d $d ]]; then d=${d%/*}; fi
  top=$(git -C "$d" rev-parse --show-toplevel 2>/dev/null || true)
  if [[ -n $top ]]; then echo "$top"; fi
done < <(grep -oE '(~|/)[A-Za-z0-9_./@+-]+' <<<"$lab_text" | sed 's/[.,;:)]*$//' | sort -u))
[[ -n $repos ]] || say "no git repo named in the lab's files; no worktrees to remove"

removed=0 kept=0
for repo in $repos; do
  json=$(wt -C "$repo" list --format json 2>/dev/null || true)
  [[ -n $json ]] || { say "wt list failed for $repo; skipped"; continue; }
  while IFS=$'\t' read -r branch path is_main dirty ahead; do
    [[ -n $branch && -n $path ]] || continue
    if ! grep -qF -- "$branch" <<<"$lab_text" && ! grep -qF -- "$path" <<<"$lab_text"; then
      continue  # worktree not named by this lab
    fi
    if [[ $is_main == true ]]; then
      say "$repo: main worktree kept"; ((kept++)) || true; continue
    fi
    if [[ -n ${PWD:-} && ($PWD == "$path" || $PWD == "$path"/*) ]]; then
      say "$path: kept (the caller is running in it)"; ((kept++)) || true; continue
    fi
    if [[ $dirty == true ]]; then
      say "$path: kept (dirty; commit or stash, then rerun)"; ((kept++)) || true; continue
    fi
    # wt remove deletes the branch only when merged, so an unmerged lab branch
    # (ahead of main: the provenance records) survives; never pass -D
    if [[ $ahead -eq 0 ]]; then
      state="branch $branch merged; wt deletes the branch"
    else
      state="branch $branch kept (ahead $ahead of main: the provenance records)"
    fi
    if [[ $apply == yes ]]; then
      wt -C "$repo" remove --foreground "$branch" >/dev/null \
        || fail "wt remove --foreground $branch (worktree $path) failed"
      say "$path: removed worktree ($state)"
    else
      say "[dry-run] $path: would remove worktree ($state)"
    fi
    ((removed++)) || true
  done < <(jq -r '
    .repo.default_branch as $d
    | .items[]
    | select(.worktree != null and .worktree.path != null)
    | [ .branch // "",
      .worktree.path,
      ((.worktree.main // false) or (.branch == $d)),
      (.worktree.changes // {} | [.staged, .modified, .untracked, .renamed, .deleted, .conflicted] | any),
      (.default_branch.ahead // 0) ]
    | @tsv' <<<"$json")
done
if [[ $apply == yes ]]; then
  say "worktrees: $removed removed, $kept kept"
else
  say "worktrees (dry-run): $removed removable, $kept kept"
fi
