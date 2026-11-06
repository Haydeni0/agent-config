---
name: local-skill
description: Use when adding or converting a machine-local skill - a skill that lives in this checkout's skills/ but stays out of git, never appearing in diffs or a fresh clone. Triggers on "machine-local skill", "local-only skill", "make this skill local", "skill without a diff", "keep this skill off github". Also covers what tooling already handles (skill map, sync, verify) so nothing else needs doing.
---

# local-skill

Machine-local skill: same shape as any other skill (`skills/<name>/SKILL.md`,
frontmatter, body) but ignored by git. It exists only on this machine's clone -
no diff, no commit, absent from a fresh clone. Sync still installs it into
native homes: sync discovers skills from the filesystem, including ignored
ones, so every harness sees it.

## Adding one

1. Write `skills/<name>/SKILL.md` as usual.
2. Ignore it per-clone, not in `.gitignore`. Append the directory to
   `.git/info/exclude`:

   ```bash
   echo 'skills/<name>/' >> .git/info/exclude
   ```

   `.git/info/exclude` is git's per-clone ignore file: untracked, never
   committed, invisible to diffs and CI. A `.gitignore` line would work as an
   ignore but is a tracked diff and leaks the skill's name into the repo -
   `.git/info/exclude` is the mechanism when the point is "no diff".

3. Link it into native homes now: `agent-config sync <harness>`. The Claude
   home symlinks the source checkout, so new Claude sessions pick it up even
   without a sync; other harnesses need the sync run.

## What tooling already handles

- **Skill map**: `scripts/check_skill_graph.py` excludes git-ignored skills
  (REQ-SKILLS-11), so the committed README map never mentions them and a
  fresh clone generates the same graph. No map regen; verify.sh stays green.
- **Sync**: ignored skills sync like tracked ones - links, not copies - so a
  later edit to the skill is live immediately.
- **Requirements contract**: no row needed; the mechanism's behavior is
  REQ-SKILLS-11, and this skill is documentation, not a behavior change.

## Converting a `.gitignore`-ignored skill

A skill previously ignored via a committed `.gitignore` line becomes
no-diff-local by moving the line: delete it from `.gitignore`, append the
directory to `.git/info/exclude` on every clone that holds the skill. Repo
references to "gitignored skills" stay accurate - the skill is still
git-ignored, just per-clone.

## Limits

- Machine-local means this clone: other machines need their own copy, by
  hand - nothing carries it.
- The skill vanishes if the checkout is re-cloned; keep a copy elsewhere if
  it matters.
- Vendored (symlinked) skill dirs are shared upstream state - never make
  them machine-local.
