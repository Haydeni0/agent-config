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

### 2026-11-02 - verify_claims rejects some true claims on citation shape: file spans cannot attest their own path, antecedents need their source cited, and a record cannot cite its own verifying run

Oracle-verifying a requirements-coverage record (REQ-SKILLS-20/21 audit, /tmp/cv-test/scratch/report-reqs.md), three flags traced to how claims were cited, not to false claims - all confirmed via `include_prompts`, which shows the verifier does strict textual entailment over the quoted span text only:

- A file span (path + line range) cannot support a claim about *where* content lives: "rows are in docs/requirements.md" was not_entailed three times while cited only to the file's own content, because the quoted content never names its file. Fix: add a span quoting a command output that names the path (`grep -n "REQ-SKILLS-2[01]" docs/requirements.md`) alongside the content span.
- A sentence whose subject is an antecedent from a prior sentence ("the row's no-restatement clause") needs the antecedent's source cited on that sentence too; adding the row text and a corroborating entry flipped the verdict to passed.
- A record cannot contain "the oracle run on this record returned no flagged claims" and pass that same run - the only entailing evidence is the run's own output, which does not exist yet (structural, not fixable by better citations). Fix: two passes - first verify with the sentence reduced to "the verify_claims MCP ran this session" (cited to earlier run outputs on the same record), then restore the full sentence citing that clean pass and re-verify; every sentence then cites a completed run.

Consequence for the fallback route: a finalised record's verification line should either document the pass history (first pass flagged N claims, later pass clean) or stop at "the MCP ran this session"; the unconditional "returned no flagged claims" phrasing only survives the two-pass restore.

### 2026-11-01 - monkeypatch.undo() mid-test reverts the autouse isolation fixtures too: a planned test synced into the real ~/.claude

The cycle D plan's S5/S6/S8 tests called `monkeypatch.undo()` to restore `_REPO_ALIASES` between two syncs. The autouse `isolated_home` and `stub_codegraph_download` fixtures in `settings-sync/tests/conftest.py` set HOME/XDG env through the same function-scoped monkeypatch instance, so undo() also reverted the isolation: the tests' second `agent-config sync claude` ran against the REAL home with `--source <pytest tmp>`. Damage: installed settings.json hooks emptied and `model` clobbered to "shared", CLAUDE.md regenerated pointing at the tmp source, nine alias links repointed at tmp, `~/.claude/custom` pruned, all per-skill/command/agent links pruned, ownership store polluted. Recovered by restoring `settings.json` and `managed.json` from the executor's pre-replace backups under `~/.local/state/agent-config/backups/`, removing the two unmanaged tmp links, then `agent-config sync claude` (+ `--force` for the differing CLAUDE.md and alias links, all incident damage) - final `agent-config check claude` clean. Fix in commit ba41840: tests restore the alias table with a second `monkeypatch.setattr` against a module-level `_NEW_ALIASES` capture; never call `monkeypatch.undo()` mid-test in this suite. Rule for test authors: mid-test state restore must use a scoped re-setattr, because fixture env isolation rides the same monkeypatch instance.

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
