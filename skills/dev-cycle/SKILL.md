---
name: dev-cycle
layer: orchestrator
description: Run the full dev pipeline (grill, test plan, spec, plan, implement, review, fix) for a feature or bugfix. Invoke only via /dev-cycle or an explicit request to run the full pipeline.
---

# dev-cycle

Run the complete development cycle for one topic: grill → test-plan → launch gate → spec → plan → implement → code-review → verify-fix. Interview stages are human-in-loop; everything after the gate is autonomous - subagent review verdicts are the gates, never user questions.

## On invocation: stage detection

The cycle unit is a package dir `.agents/plans/<slug>/` (slug = `<date>-<topic>`). Read the target project's `.agents/plans/`, first match wins:

1. No package dir for the topic → grill (creates the package). A package whose `decisions.md` has open Q entries also lands here: grill resumes until every Q is resolved or struck.
2. Package exists, no `scenarios.md`, no open Q entries → test-plan.
3. `scenarios.md` present, no `spec.md` → launch gate, then spec.
4. `spec.md` with `Reviewed: pass` marker, no `plan.md` → gate, then plan.
5. Spec and plan with pass markers, plan has ≥1 unchecked box (zero checked = fresh) → gate, then implement from first unchecked task.
6. Pass markers, plan fully checked, plan footer has `Implemented` marker, code review not yet done → gate, then review. (Cycle state lives in markers, never inferred from the git tree - a commit-gated cycle may end committed or uncommitted.)
7. Artifact with `Reviewed: fail` markers, no later pass → gate, then that artifact's review. User resolution at the gate resets that artifact's cap.
8. Pass markers, plan fully checked + `Implemented`, code review + verify-fix done → cycle complete; report, offer a new topic.

Two+ candidate packages → one plain-text question listing them. Package `decisions.md` with no D entries and no open Q entries = case 1. Hand-written artifacts (no markers) = unapproved drafts of the newest matching cycle → gate, then their review stage; once a draft gains its pass marker, re-run detection from the top so missing earlier stages run first. A spec/plan pass marker with no `## Outcome` recorded in `decisions.md` = unapproved draft (gate never passed) → run the gate; on `go`, record `## Outcome` and re-run detection from the top - the draft's markers stand, and any earlier missing stage (e.g. no `scenarios.md`) runs before the one the draft reached. In both recoveries, the gate just passed satisfies the gate requirement of the case the re-run lands on.

Legacy: a flat `<date>-<topic>-decisions.md` / `-spec.md` / `-plan.md` triple is a pre-package cycle. Read its shared basename as the package dir, and at the next gate convert, not just move: put the three files into `.agents/plans/<basename>/` as `decisions.md` / `spec.md` / `plan.md`, renumber the legacy `## Design decisions` lines as D entries, and extract the `## Test scenarios` section into `scenarios.md`.

## Artifacts (package per cycle, in the target project's `.agents/plans/<slug>/`)

- `decisions.md` - the resume anchor and reviewer input. Entries in the format sketched here: `- D<n> (<date>). **Choice.** Rejected: ...` (grill end), `## Outcome` (gate), `## Review nits` (LOW findings that survive).
- `requirements.md` - user-stated constraints (must / never / always) as `- R<n> (<date>). ... Source: user.` entries, split out of the grill.
- `scenarios.md` - test-plan output (test-plan end).
- `spec.md`, `plan.md` - write-spec / writing-plans output, footer carrying `Reviewed: pass|fail <n>` markers appended after each reviewer pass.

## The stages

1. **Grill** - invoke grill-me. At its end, file its decision log as D entries in the package `decisions.md` (`- D<n> (<date>). **Choice.** Rejected: <alternative>. <rationale>`); log lines auto-decided after `SKIP_GRILL` are filed as D entries ending `Agent-picked`; user-stated constraints (must / never / always) become R entries in `requirements.md` (`- R<n> (<date>). <statement as stated>. Source: user. Scope: new.`).
2. **Test-plan** - invoke test-plan. The orchestrator files its inline output as the package's `scenarios.md`; decline test-plan's own offer to persist elsewhere (`docs/tests/...`). Always write `scenarios.md`, even when the outcome is "no keeper tests" plus the rationale.
3. **Launch gate** - print the summary and nothing else: proposed outcome (1-2 sentences drafted from the package `decisions.md`), decisions one-liners, remaining stages, git posture (branch if on main; commits land per the user's global git rules, deferred if blocked), abort conditions, expected artifacts. Then WAIT. The user's response is confined to: confirm the outcome, correct it, or replace it - and `go` (with or without an outcome correction) is the sole entry to the autonomous zone. No flag skips the gate and no stage-skip options exist or may be offered. Only after `go`: write the confirmed outcome (proposal as-is, or the user's correction) to the package `decisions.md` as `## Outcome`, then proceed. Every invocation resuming into cases 3-7 passes the gate; case 8 and interview restarts do not.
4. **Spec** - run write-spec. Scenarios from stage 2 become the spec's acceptance-criteria section. Autonomous zone: any step where the skill would pause for user approval, the reviewer verdict stands in. Then review (below).
5. **Plan** - run writing-plans; plan saved as the package's `plan.md`. Same replacement: reviewer verdict stands in for any user-approval pause. Then review.
6. **Implement** - spawn fresh general-purpose subagent (never a fork): plan path, spec path, decisions path, instructions to follow executing-plans and invoke the tdd skill. Prompt carries the implementer contract (below). Branching follows the user's git rules; say the branch name in the gate summary. On implement completion, append `Implemented` to the plan footer.
7. **Code-review** - spawn fresh general-purpose subagent: working-tree diff, spec/plan paths, implementer's deviation log, instruction to run the code-review skill in full orchestrator mode (it spawns its own lens subagents). The deviation log tells it where the implementer made in-flight judgment calls - where to look hardest.
8. **Verify-fix** - main agent, inline: code-review already deduped/scored findings (Critical/Major/Minor). For each: judge real or not; fix real; discard rest with stated reason. Critical/Major map to "fix" candidates, Minor to judgment calls. Single pass, no re-review.
9. **Final report** - outcome vs `## Outcome` (met/not met, evidence); deviation log; fixed + discarded findings with reasons; deferred commits if any (gate was closed); flagged deviations from grill decisions.

## Review machinery

Reviewer = fresh general-purpose subagent (never a fork - shared context = shared blind spots). Inputs: artifact path(s), package `decisions.md`, repo read access. Spec/plan reviewers return numbered findings: severity (HIGH/MEDIUM/LOW), problem, fix. Fail = any HIGH or MEDIUM. LOW-only = pass; append nits to `## Review nits`.

**Loop:** findings → revise artifact → re-review (changed sections focus; reviewer gets its own prior findings). Cap: initial + 2 re-reviews per artifact per resolution attempt. After round 2, only a HIGH finding buys another round; MEDIUM findings are fixed and recorded without re-review, LOW findings are appended to `## Review nits`. Marker numbering continues over the artifact's lifetime - the cap resets at gate resolution (case 7), the count does not. Still failing (HIGH) after the second re-review → abort: full report (stage, findings, history, paths, what resolving looks like). Artifacts stay on disk; recovery = user resolves, re-invokes, detection resumes.

**Reviewer checklists (embed in the spawn prompts):** Spec reviewer - internal consistency, no placeholders, faithful to the recorded decisions, single-plan scope, reads the codebase to verify factual claims. Plan reviewer - two axes: (a) plan-vs-codebase (file paths exist, structure claims match reality, task order respects dependencies), (b) plan-vs-design (every spec acceptance criterion covered, no invented scope, faithful to decisions).

## Orchestrator-side escalation handling

On implementer return - **BLOCKER** (plan-level): apply the proposed revision to the plan file, re-run the plan reviewer on the changed sections (counts against the plan's cap-2), respawn the implementer from the checkpoint task. **SPEC-CONFLICT** (spec-level): abort the run - full report to the user (the contradiction, the implementer's evidence, artifact paths); spec and recorded decisions are user-owned, no autonomous path changes them.

## Implementer contract (in the spawn prompt)

You execute the plan file. You NEVER ask the user questions. Git authorization follows the user's global rules - the gate decides whether a commit lands. Plan "Commit" steps are logical per-task commits: if a commit is blocked (gate closed), record "commit deferred at task N - gate closed" in your deviation log and CONTINUE - the run never stops for git authorization. When all tasks complete, append `Implemented` to the plan footer. Blocked comes in three tiers:
- Implementation detail (naming, in-task structure): decide, log deviation + reasoning, continue.
- Plan-level (task wrong/missing/mis-ordered; in-task approach won't work): STOP. Return BLOCKER: task number, what reality shows, proposed plan revision. Do not fix the plan yourself.
- Spec-level (reality contradicts the spec or a D entry in the package `decisions.md`): STOP. Return SPEC-CONFLICT: the contradiction, evidence. Do not proceed.
Return: completion summary + full deviation log.

## Abort rules

Three abort triggers, all terminate with a full report - they never pause to ask mid-run: (1) review cap exceeded after the second re-review; (2) SPEC-CONFLICT (spec-level escalation - user-owned decisions); (3) subagent crash after one retry. Abort during interview stages: restart that stage from the top (human is present).

## Existing project documents

Use the global legacy-document rule before creating or resuming plans/backlogs: canonical `.agents` when present, legacy `.claude` when it is the only copy, reconcile both before resuming, editing, or migrating. Preserve IDs and checkbox progress.
