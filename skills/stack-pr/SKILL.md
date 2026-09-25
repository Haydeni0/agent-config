---
name: stack-pr
description: Use when creating, rebasing, verifying, or repairing a stack of PRs on GitHub - multiple PRs where each bases on the previous one's head branch. Triggers on "stacked PRs", "PR stack", "rebase the stack", "stack of PRs", "create PRs from these commits", or when a branch-scoped CI failure or a PR showing "0 changed files"/merged-when-it-shouldn't is diagnosed on a stack. Also use when amending or force-pushing any branch that has PRs stacked on top of it.
---

# Stack PR

Build from immutable commit boundaries, validate each PR's own patch, then verify
GitHub's actual head, base, and checks. Local Git success alone proves neither
publication nor stack health.

## Preflight and stack map

1. Resolve the repository, push remote, stack base, and ordered PR dependencies.
   Confirm head/base repositories for forks before choosing remotes or refspecs.
2. Check worktrees, dirty files, and any active rebase/cherry-pick. Preserve user
   work; finish or abort an existing operation deliberately before starting another.
3. Fetch relevant refs, inspect divergence, and read PR state. Capture **every old
   parent, head, and reviewed remote tip before changing any branch**. If a parent
   already moved, recover its old boundary from saved refs/reflogs and inspect the
   commit range. Missing or ambiguous boundaries block rewriting.
4. Inspect CI triggers against each actual PR base: branch/path filters, events,
   required checks, and concurrency. Record how each PR will receive valid checks.

Keep `.agents/stacks/<slug>.json`. Read legacy `.claude/stacks/<slug>.json` when
present; reconcile both copies before migrating either. The map records reviewed
intent; live Git/GitHub observations must be checked against it.

```json
{
  "repo": "owner/repository",
  "remote": "origin",
  "base": "trunk",
  "prs": [
    {
      "branch": "hayden/example-pr1",
      "pr": 123,
      "title": "Example change",
      "parent_sha": "<full SHA at the start of this PR's own range>",
      "head_sha": "<full validated head SHA>",
      "remote_sha": "<full reviewed remote head SHA>",
      "is_draft": true,
      "own_files": 4
    }
  ]
}
```

Each branch includes its ancestors; only `parent_sha..head_sha` belongs to that
PR. Multiple own commits are valid. `own_files` is a warning signal, not proof of
patch identity. For unpublished branches use `pr: null` and `remote_sha: ""` after
confirming the remote ref is absent. Record CI findings alongside the map.

Before rewriting, save the map as an operation snapshot and create named backup
refs for every old parent/head. Keep these through remote verification. Record
candidate SHAs and publication progress separately so an interrupted operation
retains both its old boundaries and its intended new tips.

## Create

1. Inspect the source range and group commits into the requested PR units. Create
   `hayden/` branches at the group tips, oldest first. Review each own patch and
   record its boundaries **before** publishing; GitHub's later file count must
   not become the sole definition of correctness.
2. Publish through **Publish**, using an empty expected remote SHA for new refs.
3. Create draft PRs oldest first, passing `--repo`, `--head`, and explicit `--base`
   (the stack base for the first PR; the previous head branch thereafter). Use
   `gh pr create --draft --body-file <file>` with the intended title/body.
4. Save PR numbers and run **Verify**. Preserve existing draft/ready state when
   updating an existing PR; record changes as observations.

## Rebuild bottom-up

Use the operation snapshot's old boundaries throughout. For each affected PR,
`new_parent` is the validated replacement parent SHA (or new stack-base SHA).
Use fresh `hayden/` scratch and backup branch names; resolve variables to verified
full SHAs before running these commands:

```bash
git branch "$backup" "$old_head"
git switch --create "$scratch" "$old_head"
git rebase --no-update-refs --onto "$new_parent" "$old_parent" "$scratch"
new_head=$(git rev-parse HEAD)
git range-diff "$old_parent..$old_head" "$new_parent..$new_head"
git diff "$new_parent" "$new_head"
```

`old_parent` is the exclusive replay boundary. Using `old_parent~1` replays an
extra parent commit. Reading the parent branch after moving it loses the old
boundary. The same recipe handles one or several own commits.
`--no-update-refs` keeps backup and original branches fixed even when the user's
Git configuration enables automatic ref updates.

Review every changed/dropped patch in `range-diff`, the resulting own diff, and
relevant tests. Unexpected empty patches require investigation: distinguish
already-integrated work from accidentally lost work before accepting a drop.
On conflicts, resolve against intended behavior and validate again; abort the
scratch operation if that intent cannot be established.

Build and validate all affected descendants before publishing. Update original
local branches only after confirming they still match the snapshot and accounting
for worktrees using them. Keep scratch/backup refs if any check fails.

## Publish

Apply the user's commit/push authorization gate to **every** such action,
including repair and CI retriggers. Rewriting a stack does not authorize merging.

Use an explicit lease against the remote SHA captured and reviewed in preflight.
For the environment-gate authorization path:

```bash
printenv PUSH_AUTHORISED && git push \
  --force-with-lease="refs/heads/$branch:$expected_remote_sha" \
  "$remote" "$new_head:refs/heads/$branch"
```

An empty expected SHA requires that the ref is still absent. Publish bottom-up;
after each push confirm the exact remote ref and, for an existing PR, its GitHub
head. Verify new PRs after creation. Record progress.
Treat descendant comparisons as pending until their planned tips are published.
Run full **Verify** once the affected stack is published.

**Lease rejection stops publication.** Fetch to inspect the new work, preserve
both versions, reconcile changes, and rebuild affected descendants. Capture a
new expected SHA only after that review. Fetching and blindly retrying renews
permission to overwrite unreviewed work; never substitute bare force.

## Verify

Query each PR explicitly, for example:

```bash
gh pr view "$pr" --repo "$repo" --json \
  state,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,headRepositoryOwner,changedFiles,isDraft,statusCheckRollup
git ls-remote --heads "$remote" "refs/heads/$branch"
```

Check:

- Head name/repository and GitHub head SHA match the validated candidate and exact
  remote branch SHA. Existence alone is insufficient.
- Base name/repository matches the dependency map. Compare its current tip with
  the validated parent; movement requires refreshing and revalidating the diff.
- Actual GitHub own patch matches reviewed intent and the validated local range.
  Check ancestry and changed paths/content; matching file counts can hide losses.
- Lifecycle state is explained. Unexpected `MERGED`, `CLOSED`, missing refs, or an
  empty own diff trigger **Repair** investigation, not an automatic diagnosis.
- Required checks correspond to the current candidate or GitHub's test merge for
  its current head/base. Stale green checks cannot validate a different head.

Report one row per PR: head/base identity, patch, lifecycle, CI, and draft state.
Distinguish failed, pending, and verified. Record reviewed map updates after
verification; preserve the operation snapshot. Pending CI means CI is pending.
Identity/patch mismatches stop further publication or merging until reconciled.

## Repair and CI

Diagnose from refs, diffs, PR timeline, merge metadata, and logs before mutating.

- **Unexpected merge:** commits can reach the base via another PR or direct push
  and legitimately mark a PR merged indirectly. Verify inclusion first. If work
  remains missing, restore it from saved refs onto the correct base and validate
  the remaining patch before creating a replacement draft PR. A merged PR cannot
  be reopened.
- **Wrong base:** inspect the actual target, then try `gh pr edit --base <target>`.
  If rejected, inspect the error and current stack state. Recreating is a last
  resort: preserve title/body/metadata, link the replacement, and retarget affected
  descendants. Verify the replacement before retiring an open predecessor.
- **Missing head:** determine whether deletion followed an expected merge. Restore
  only an intended live branch from a validated SHA with an absent-ref lease;
  inspect PR state and reopen a closed, unmerged PR when appropriate.
- **Absent CI:** inspect branch/path filters and supported events. Manual dispatch
  requires `workflow_dispatch`, a workflow present on the default branch, and
  compatible event handling. Confirm resulting checks attach to the intended PR
  revision. Propose repo-wide trigger changes separately from stack repair.
- **Red gatekeeper:** inspect its failing log, run attempts, event, SHA, and
  concurrency configuration. Cancelled siblings alone do not establish cause.
  Rerun eligible checks when appropriate. An empty commit is a last resort after
  confirming a new PR event is necessary; apply both authorization gates, rebuild
  affected descendants, and reverify the resulting revision.

## Merge order and post-merge

When merging is authorized, merge bottom-up only after the intended revision's
required checks and reviews pass. Confirm the merge result and method on GitHub.

GitHub documents automatic child retargeting after deletion of a merged head
branch; verify the actual base instead of assuming it moved. Retarget the next PR
to the recorded merge target where needed. After squash/rebase merge, replay only
remaining PRs' own commits using the saved **old** parent boundaries. Revalidate
all affected descendants against the actual new base. Update the active map while
retaining the completed entry and operation snapshot for recovery.

## References

- [Git rebase ranges](https://git-scm.com/docs/git-rebase)
- [Explicit push leases](https://git-scm.com/docs/git-push)
- [Indirect merges](https://docs.github.com/en/pull-requests/reference/pull-request-merges)
- [Post-merge retargeting](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/merging-a-pull-request)
- [Workflow event requirements](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
