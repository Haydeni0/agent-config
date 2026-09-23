---
name: stack-pr
description: Use when creating, rebasing, verifying, or repairing a stack of PRs on GitHub - multiple PRs where each bases on the previous one's head branch. Triggers on "stacked PRs", "PR stack", "rebase the stack", "stack of PRs", "create PRs from these commits", or when a branch-scoped CI failure or a PR showing "0 changed files"/merged-when-it-shouldn't is diagnosed on a stack. Also use when amending or force-pushing any branch that has PRs stacked on top of it.
---

# Stack PR

Create, rebase, and verify stacks of GitHub PRs safely. The skill's core claim:
**git's local success says nothing about GitHub's stack state.** Every operation ends
with a GitHub-side verification, because that is where stacked-PR damage happens and
it is often irreversible (auto-retargeting, merged-empty PRs, deleted branches).

## Model

A stack is an ordered list of (PR number, head branch, expected own-diff), where each
PR's base is the previous PR's head branch. Branches carry exactly one PR's commits
(ideally one commit each). The map file is ground truth for what "healthy" means:

`.claude/stacks/<slug>.json`
```json
{
  "slug": "flpm-246",
  "base": "main",
  "prs": [
    {"branch": "hayden/flpm-246-pr1", "pr": 975, "own_files": 4, "title": "[REFACTOR] ..."},
    {"branch": "hayden/flpm-246-pr2", "pr": 979, "own_files": 20, "title": "[CHORE] ..."},
    {"branch": "hayden/flpm-246-pr3", "pr": 980, "own_files": 14, "title": "[REFACTOR] ..."}
  ]
}
```

`own_files` = the number of files in that PR's diff against its base. Record it at
create time; verification compares against it later.

## Create

0. **Preflight: check the repo's CI triggers.** Grep `.github/workflows/` for
   `pull_request` triggers scoped `branches: [main]` (or any branch filter). If
   present, stacked PRs - whose bases are other branches - will get no CI at all.
   Either fix the triggers first (drop the `branches:` filter; see research-lpm
   PR #981 for the pattern) or plan on `gh workflow run <wf> --ref <branch>` per
   stacked head, and note it in the map. Do not discover this after the first
   rebase push.
1. Resolve the branch base (usually `main`) and the source branch holding N stacked
   commits. For each commit i (oldest first): create branch `<prefix>-prN` at that
   commit. One branch per commit, in stack order.
2. Push all branches (respect the user's git gates - push authorization rules apply
   to each push in this skill).
3. For each PR, oldest first: `gh pr create --draft --base <previous branch or the
   base> --head <branch> --title <title>`. **Always pass `--base` explicitly** -
   `gh` defaults to the default branch and silently mis-bases every stacked PR.
4. Read back each PR's `changedFiles` from GitHub, write the map file, run
   **Verify**.

## Rebase (after the base moved, or a lower stack commit changed)

Never guess `--onto` arguments. Read the map file and compute the replay range from
recorded SHAs, not branch positions:

```
# branch N's own commits = everything after its parent branch's recorded tip
parent_tip=$(git rev-parse <previous branch>)        # replay range start: exclusive
git checkout <branch N>
git rebase --onto <new parent tip> $parent_tip~1 <branch N>   # only if branch N has >1 own commit
```

For a one-commit branch, prefer explicit cherry-pick onto a scratch branch - it
cannot silently replay zero commits:

```
git checkout -B <branch N> <new parent tip>
git cherry-pick <recorded commit sha for branch N>
```

Rules:
- Rebase bottom-up (lowest branch first), each onto the new position of its parent.
- After each branch, immediately diff-check: `git diff <parent>..<branch> --stat`
  must match that PR's recorded `own_files`. A zero-file diff means the rebase
  dropped the commit - STOP, do not push.
- Push with `--force-with-lease`, bottom-up. If the lease rejects, `git fetch` that
  one ref and retry - never drop to a bare `--force`.
- Run **Verify** after all pushes. Fix anything it reports before declaring done.

## Verify (run after every create, rebase, push, or merge in the stack)

For each PR in the map, query GitHub (not local git) and assert ALL of:

1. `state == "OPEN"` (or the user has just said it merged). A `MERGED` PR the user
   did not merge is the empty-diff auto-merge failure mode - see **Repair**.
2. `baseRefName == previous PR's head branch` (first PR: the stack base).
   GitHub auto-retargets stacked PRs when a base's head moves; a retarget is often
   correct (parent merged) but must be an explicit finding, never silent.
3. `changedFiles` equals the recorded `own_files`. Zero changed files = broken.
4. The head branch exists on the remote (`git ls-remote origin <branch>` non-empty).
   GitHub deletes head branches of merged PRs; a missing branch with an OPEN PR
   means the PR is orphaned.

Also record and report (observations, not failures): `isDraft` vs the map's record -
draft/ready flips happen on the user's side and Verify should surface them, not
trip on them.

Print a one-line-per-PR table with pass/fail per assertion. Any fail = the stack is
broken: do not proceed with merges or further rebases until repaired.

**CI race diagnosis.** All real suites green but the repo's gatekeeper check
(e.g. `check-statuses`) red after a force-push = push race: `concurrency:
cancel-in-progress` cancelled the superseded run generation on the pushed SHA and
the gatekeeper judged the cancellation a failure. Check the run list for that SHA:
cancelled sibling runs alongside green survivors confirm it. Repos whose gatekeeper
is cancellation-tolerant (skips a cancelled run only when a successful sibling of
the same workflow exists - see research-lpm PR #984) self-heal: the fresh
gatekeeper run from the same push goes green; just wait for it. Repos without
the fix: do NOT try `gh workflow run` on the gatekeeper - gatekeeper scripts
typically resolve their target SHA/PR from the `pull_request` payload only, so a
dispatch run no-ops. The working lever is a fresh PR event: an empty commit
pushed to the branch (`git commit --allow-empty -m "chore: retrigger CI"`).

## Repair (known GitHub-side failure modes)

- **PR shows MERGED with ~0 changes, user never merged it**: an earlier bad rebase
  made head == base; GitHub treated it as empty and auto-merged, deleting the
  branch. Merged PRs cannot be reopened. Recovery: `git push origin <branch>`
  (recreates the remote ref), close the dead PR, `gh pr create --draft --base
  <parent> --head <branch>` with the original title/body (note in the body that it
  recreates #N). Update the map file with the new PR number, run **Verify**.
- **PR base auto-retargeted wrong** (e.g. grandparent instead of parent): `gh pr
  edit --base` fails with "Cannot change the base branch because the pull request
  is part of a stack" - GitHub stack bookkeeping is stuck. Recovery: close the PR,
  recreate with the correct `--base` (the check runs at edit time, not create
  time). Update the map.
- **Head branch missing on remote**: re-push it, then check whether GitHub reopened
  the PR by itself; if not, recreate per above.
- **CI absent on stacked PRs**: workflows with `pull_request: branches: [main]`
  never fire for PRs whose base is another branch. Check for runs at the head SHA;
  if none and the repo still has branch-scoped triggers, `gh workflow run <wf>
  --ref <branch>` for the missing suites and note the repo should widen its
  triggers (research-lpm did this in #981; its gatekeeper learned cancellation
  tolerance in #984). `check-workflow-statuses`-style gatekeepers associate
  dispatched runs with the PR only when the dispatch shares the head SHA - verify
  via the PR's checks, not the run list.

## Merge order and post-merge

Merge strictly bottom-up. After PR1 merges to the base branch:

1. The next PR's base retargets to the merge target (GitHub does this for stacks;
   verify it happened - if it still points at the merged branch, `gh pr edit
   --base main`; if that fails due to stack bookkeeping, close + recreate).
2. If the merge was a squash/rebase-merge, the next PR's diff may now show
   conflicts or stale-parent artifacts - rebase it onto the new base tip per
   **Rebase**, then Verify.
3. Update the map file (drop the merged PR, re-point the next PR's base).

Never merge a PR whose own-diff is empty, and never let Verify-fails ride: every
one of them is a stack corruption in progress.
