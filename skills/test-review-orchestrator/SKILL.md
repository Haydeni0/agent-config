---
name: test-review-orchestrator
layer: worker
description: Use when user wants a combined test review covering both coverage gaps and redundancy on the current branch/PR before deciding what to implement.
deps: [test-trim, test-add]
---

# Test Review Orchestrator

On invocation, immediately dispatch a single agent to run the full workflow in isolation. Do not run the orchestration inline.

## On Invocation

Dispatch:

```
Agent(
    description="PR test review: trim + add",
    prompt=<agent prompt below>
)
```

Present the agent's output directly to the user, then ask:

`Pick items to implement by number (for example: 1,3,4).`

## Agent Prompt

Use this prompt verbatim:

---

You are a test review orchestrator. Review the current branch/PR for both test redundancy and missing coverage. Review-only — do not edit files.

**Step 1 — Scope**

Prefer `origin/main...HEAD` unless the user specified a base branch or `--since <commit>`. If `--since <commit>` provided, compute `BASE=$(git merge-base <commit> HEAD)` and use that.

```bash
git diff --name-only $BASE...HEAD
git diff --stat $BASE...HEAD
git log --oneline $BASE..HEAD
```

**Step 2 — Parallel dispatch**

Dispatch two subagents in parallel:

1. **Trim agent** — apply the `test-trim` skill. Return prioritized findings and numbered trim proposals. No edits.
2. **Add agent** — apply the `test-add` skill. Return prioritized findings and numbered test-add proposals. No edits.

Each must return: `Critical/Major/Minor` findings, a `Keep` list, and numbered proposed actions.

**Step 3 — Merge**

Combine outputs:
1. Merge duplicates by location + intent.
2. Keep stronger rationale where findings overlap.
3. Resolve trim-vs-add conflicts explicitly (flag as `both` if a test should be replaced, not just trimmed).
4. Preserve original priority unless conflict requires escalation.

Then inline quality pass before publishing:
- Drop findings with no concrete action or unclear location.
- Flag contradictions (e.g. trim and add targeting the same test).
- Normalize severity: only `Critical` if regression risk or core behavior is unguarded.

**Step 4 — Output**

```markdown
## Findings

### Critical
1. `path::symbol`: problem, risk, fix.

### Major
1. ...

### Minor
1. ...

## Keep
1. `path::symbol`: reason.

## Recommended Actions
1. `file` — trim|add|both — benefit — risk if skipped
2. ...
```

---
