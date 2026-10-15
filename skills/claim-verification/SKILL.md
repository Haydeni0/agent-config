---
name: claim-verification
layer: worker
description: Use before sending any claim-bearing message - a chat answer, a message to a peer agent, a subagent return, a status file, a doc finalise, or a PR or Linear post that asserts facts about the codebase, environment or work state. Checks each claim against fresh evidence, through the verify_claims MCP when present, else a written self-pass plus, for terminal messages, a fresh-context judge.
deps: []
---

# claim-verification

## Overview

Every factual claim leaving this session is checked against evidence gathered in this session before it is sent. A report from anyone else - a subagent, a peer agent, a doc, a README, your own earlier observation - is a claim to check, never evidence.

## When

A **claim-bearing message** is any outgoing text asserting a fact about the codebase, environment or work state:

- a chat answer to the user;
- a message to a peer agent (mailbox, overseer, orchestrator) or a subagent's return;
- persisted text read as status: a status file, a finalised doc, a PR description, a Linear post.

A **terminal message** is the last word on a piece of work: a completion report, a finalised doc, a PR or Linear post, a final summary to an overseer or the user.

## Procedure

1. **List the claims.** Every sentence in the draft that could be true or false about code, environment or work state.
2. **Gather evidence** for each claim per the Evidence table, fresh in this session. Evidence read before a step that could change it (a script run, a migration, a merge, a push) is stale: re-read after the step.
3. **Route:**
   - **verify_claims MCP present** (the tool list shows a `verify_claims` tool, e.g. `mcp__verifier__verify_claims`): call it with the draft carrying `[S#]` citations and the spans, in the shape the tool's own description defines. Fix or remove each flagged sentence and call again, until it passes or the flagged claims are cut. No judge on top - the oracle is already independent of you.
   - **MCP absent, any message:** write the self-pass below. Each unverified claim is verified, deleted, or tagged `[unverified]` before sending.
   - **MCP absent, terminal message:** the self-pass, then a fresh-context judge subagent whose brief is filled from `judge-brief.md` with the claims and their evidence spans. Fix or tag every claim it does not pass. Stamp the message `degraded - LLM-judged, not oracle-judged`. In a harness without subagents, run the judge as a separate inline pass and add `same-session judge` to the stamp.
4. **Send** only the fixed draft.

Never shell out to a `verify-claims` binary; the oracle is the MCP tool or the fallback above.

### Self-pass format

Kept in working notes, or appended to the message when the reader needs it:

```
claim -> evidence -> verdict
- <claim> -> <command output / file:line / tool result read this session> -> verified | unverified
```

## Evidence table

| Claim | Requires | Not sufficient |
|---|---|---|
| Tests pass | Test command output: 0 failures, run now | A previous run; a report that they pass |
| Linter clean | Linter output: 0 errors | A partial check |
| Build succeeds | Build command: exit 0 and output read | Linter passing |
| Bug fixed | The original symptom re-run: passes | Code changed |
| Regression test works | Red-green: revert the fix -> fails, restore -> passes | Test passes once |
| Agent or worker completed | VCS diff and artifacts inspected, its verification re-run by you | The agent's report |
| Requirements met | Line-by-line check against the requirements | Tests passing |
| A value in code or config | The source of truth, read now | Docs, README, comments, memory |
| A doc or README says X | The source the doc describes | The doc itself |
| State observed earlier | A re-read after the last step that could change it | The earlier read |
| Merged / pushed | A live remote read: `git ls-remote`, `gh pr view` | The exit code of the push or merge |
| A command succeeded | Its output, read | Its exit code alone |

## Red flags - stop

- "Per the report / worker / README, X" with no independent check.
- Quoting a value read before a step that rewrites it.
- Skipping the pass because a claim "is obvious" or the message is "just a status update".
- A terminal message going out with no oracle call and no judge.
