---
summary: "Agent long-term memory - agent-config lessons learned"
read_when:
  - Starting work in this repo
  - Hitting a gotcha that might recur
  - Changing sync targets, overlays, native homes, hook trust, or launchers
---

# MEMORY.md - agent-config

Long-term memory for AI agents working in this repo. Read at session start;
append to it when you discover or fix something non-obvious. Do not duplicate
`AGENTS.md` rules here; an entry expands on a rule with the evidence (what
broke, the fix, the commit), since that provenance is the value this file adds
over the rule alone.

Rules:
- One entry per learning, newest at top.
- Date + one-line summary as a `###` heading, then the detail.
- Only verified facts confirmed this session; no guesses.
- Reference the commit that fixed it, where one exists.
- Prune: merge or drop entries whose constraint no longer holds; when an
  entry's evidence stabilizes into a standing rule, promote it to `AGENTS.md`
  and drop the entry.

## Learnings

### 2026-10-06 - WorktreeRemove never fires for hook-created git worktrees; agent worktrees leak without manual `wt remove`

Claude Code 2.1.291 (latest at the time) does not fire `WorktreeRemove` for git worktrees a `WorktreeCreate` hook created - the event only reaches non-git worktrees. Upstream bug anthropics/claude-code#74708, closed stale, never fixed. The Claude harness wt wiring (REQ-HOOKS-06, commit 2a77ded) relies on that event to `wt remove` agent worktrees, so every worktree-isolated subagent and headless `claude -w` session leaves its worktree AND branch behind.

Verified by instrumenting a fresh headless session with project-level hooks (created before launch - hooks load at session start only): `WorktreeCreate` fires and is logged, `WorktreeRemove` never fires; the deployed hook itself removes cleanly when run manually (`exit 0`, worktree + branch gone). Upstream worktrunk main also ships a `WorktreeRemove` hook, but no hook can help - the event never reaches it. Their docs still claim the lifecycle "routes cleanup", which is false on current Claude Code.

Workaround is the rule in `rules/global.md`: the parent agent removes the worktree once the subagent finishes - `wt remove --foreground <branch>`, branch = last path segment of the worktree path. Never remove a running agent's worktree. If Claude Code ever fixes #74708, drop the rule and this entry.

### 2026-10-14 - A mechanical rule landing mid-flight is not followed by the in-flight flow: the tranche cycle never wrote its own state lines

The agent-state-machine tranche added stage-end `state:` writes to dev-cycle
mid-session, and the very cycle that shipped the rule (2026-10-14-agent-
state-machine-spike) ran to completion without writing a single state line -
detection silently took the absent-line legacy fallback the whole way. The
non-obvious cause: "absent = legal legacy" makes omission a silent no-op, so
nothing fails when the new discipline is skipped; the orchestrator was also
mid-habit from the pre-tranche skill text.

Lesson: when a skill gains a new must-do mechanical step, verify adoption on
the first subsequent run - do not assume text edits change in-flight behavior.
The research-spike handoff (/tmp/handoff-research-spike-skill.md, 2026-10-14)
instructs the next cycle to do the state writes and file the miss as an X
entry. If a future cycle again completes with an absent state line on its own
package, consider making the first stage's state write mechanically prompted
(a hook) rather than prose.
