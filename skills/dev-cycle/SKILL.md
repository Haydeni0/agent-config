---
name: dev-cycle
layer: orchestrator
description: Run the full dev pipeline (grill, test plan, spec, plan, implement, review, fix) for a feature or bugfix. Invoke only via /dev-cycle or an explicit request to run the full pipeline.
deps: [grill-me, test-plan, write-spec, writing-plans, executing-plans, tdd, code-review, work-package, requirements]
---

# dev-cycle

Run the complete development cycle for one topic: grill → test-plan → launch gate → spec → plan → implement → code-review → verify-fix. Interview stages are human-in-loop; everything after the gate is autonomous - subagent review verdicts are the gates, never user questions.

## On invocation: stage detection

Read the package `decisions.md` first line. When a `state:` line is present it is authoritative: route to the named stage directly (state `grill` -> case 1, `test-plan` -> case 2, `spec` -> case 3, `plan` -> case 4, `implement` -> case 5, `code-review` -> case 6, `verify-fix` -> stage 8 directly - no legacy case represents it, do not route it to case 6 whose precondition is the opposite, `complete` -> case 8). `verify-fix` is an autonomous-stage resume: pass the gate first, exactly like cases 3-7. A package whose state is a debug value (`root-cause`, `pattern-analysis`,
`hypothesis`, `implementation`, `resolved`) is a systematic-debugging
investigation, not a dev-cycle unit: say so and stop - resuming it is that
skill's job. A package at `state: research` is a research spike in
progress, not a dev-cycle unit: say so and stop - resuming it is
research-spike's job. File presence and markers refine within the named stage but
never override it. One exception: open Q entries pull the state back to `grill` - rewrite the state line to `grill` and resume case 1 - never while the state is `research` (research-spike owns the line until its terminal transition; a spike attached to a grill package holds open Qs throughout). A state value outside the enum, or a malformed state line: say so and stop -
do not guess a stage and do not fall through to the cases (the lint names the
allowed values; fix the line first). Absent `state:` line = legacy package:
use the file-presence cases below. The mapping is not bijective by design: case 7 (fail-marker recovery) refines within `spec`/`plan`, and `verify-fix` is reachable only via the state line.

The cycle unit is a package dir `.agents/work/<slug>/` (slug convention: the work-package skill). Read the target project's `.agents/work/`, first match wins:

1. No package dir for the topic → grill (creates the package). A package whose `decisions.md` has open Q entries also lands here: grill resumes until every Q is resolved or struck.
2. Package exists, no `scenarios.md`, no open Q entries → test-plan.
3. `scenarios.md` present, no `spec.md` → launch gate, then spec.
4. `spec.md` with `Reviewed: pass` marker, no `plan.md` → gate, then plan.
5. Spec and plan with pass markers, plan has ≥1 unchecked box (zero checked = fresh) → gate, then implement from first unchecked task.
6. Pass markers, plan fully checked, plan footer has `Implemented` marker, code review not yet done → gate, then review. (Cycle state lives in markers, never inferred from the git tree - a commit-gated cycle may end committed or uncommitted.)
7. Artifact with `Reviewed: fail` markers, no later pass → gate, then that artifact's review. User resolution at the gate resets that artifact's cap.
8. Pass markers, plan fully checked + `Implemented`, code review + verify-fix done → cycle complete; report, offer a new topic.

Two+ candidate packages → one plain-text question listing them. Package `decisions.md` with no D entries and no open Q entries = case 1. Hand-written artifacts (no markers) = unapproved drafts of the newest matching cycle → gate, then their review stage; once a draft gains its pass marker, re-run detection from the top so missing earlier stages run first. A spec/plan pass marker with no `## Outcome` recorded in `decisions.md` = unapproved draft (gate never passed) → run the gate; on `go`, record `## Outcome` and re-run detection from the top - the draft's markers stand, and any earlier missing stage (e.g. no `scenarios.md`) runs before the one the draft reached. In both recoveries, the gate just passed satisfies the gate requirement of the case the re-run lands on.

Legacy cycles (flat file triples) are converted per the work-package skill - load it when a package's shape does not match its contract.

## Artifacts (package per cycle, in the target project's `.agents/work/<slug>/`)

File roles, entry formats, ID rules, and marker formats are the work-package skill's contract - load it before reading or writing any of these. This skill defines only which stage produces which file: grill writes D/R entries (`decisions.md`/`requirements.md`), test-plan writes `scenarios.md`, spec/plan stages write `spec.md`/`plan.md` and carry `Reviewed:` markers appended after each reviewer round, the gate writes `## Outcome`, the implement stage appends `Implemented` to the plan footer and files the returned deviation log under `## Deviation log`, and surviving LOW findings go to `## Review nits`.

## The stages

1. **Grill** - invoke grill-me. At its end, file D entries and R entries per the work-package entry formats (load that skill): the decision log as D entries in the package `decisions.md`, log lines auto-decided after `SKIP_GRILL` as D entries ending `Agent-picked`, user-stated constraints (must / never / always) as R entries in `requirements.md`. The stage's final action writes the next state value to the `decisions.md` state line (`state: test-plan`).
2. **Test-plan** - invoke test-plan. The orchestrator files its inline output as the package's `scenarios.md`; decline test-plan's own offer to persist elsewhere (`docs/tests/...`). Always write `scenarios.md`, even when the outcome is "no keeper tests" plus the rationale. The stage's final action writes the next state value to the `decisions.md` state line (`state: spec`).
3. **Launch gate** - print the summary and nothing else: proposed outcome (1-2 sentences drafted from the package `decisions.md`), decisions one-liners, remaining stages, git posture (branch if on main; commits land per the user's global git rules, deferred if blocked), abort conditions, expected artifacts. Then WAIT. The user's response is confined to: confirm the outcome, correct it, or replace it - and `go` (with or without an outcome correction) is the sole entry to the autonomous zone. No flag skips the gate and no stage-skip options exist or may be offered. Only after `go`: write the confirmed outcome (proposal as-is, or the user's correction) to the package `decisions.md` as `## Outcome`, then proceed. Every invocation resuming into cases 3-7 passes the gate; case 8 and interview restarts do not.
4. **Spec** - run write-spec. Scenarios from stage 2 become the spec's acceptance-criteria section. Autonomous zone: any step where the skill would pause for user approval, the reviewer verdict stands in. Then review (below). The stage's final action writes the next state value to the `decisions.md` state line (`state: plan`).
5. **Plan** - run writing-plans; plan saved as the package's `plan.md`. Same replacement: reviewer verdict stands in for any user-approval pause. Then review. The stage's final action writes the next state value to the `decisions.md` state line (`state: implement`).
6. **Implement** - spawn fresh general-purpose subagent (never a fork): plan path, spec path, decisions path, instructions to follow executing-plans and invoke the tdd skill. Prompt carries the implementer contract (below). Branching follows the user's git rules; say the branch name in the gate summary. On implement completion, append `Implemented` to the plan footer, then file the implementer's returned deviation log into the package `decisions.md` under a `## Deviation log` heading - the subagent reply dies with the session, and stages 7 and 9 read the log from this durable copy. The stage's final action writes the next state value to the `decisions.md` state line (`state: code-review`).
7. **Code-review** - spawn fresh general-purpose subagent: working-tree diff, spec/plan paths, the implementer's `## Deviation log` section from the package `decisions.md`, instruction to run the code-review skill in full orchestrator mode (it spawns its own lens subagents). The deviation log tells it where the implementer made in-flight judgment calls - where to look hardest. Before writing the state line, file the deduped/scored findings into the package `decisions.md` under a `## Review findings` heading (numbered, severity, one line each) - verify-fix triages from this durable copy, so it survives compaction and dead sessions. The stage's final action writes the next state value to the `decisions.md` state line (`state: verify-fix`).
8. **Verify-fix** - main agent, inline: read the `## Review findings` section the code-review stage filed in `decisions.md` (the subagent reply was a mirror; the section is the source - use it when resuming after compaction or a dead session). code-review already deduped/scored findings (Critical/Major/Minor). For each: judge real or not; fix real; discard rest with stated reason, appending the disposition (fixed / discarded: reason) beneath the finding in the section. Critical/Major map to "fix" candidates, Minor to judgment calls. Single pass, no re-review. The stage's final action writes the next state value to the `decisions.md` state line (`state: complete`).
9. **Final report** - outcome vs `## Outcome` (met/not met, evidence); deviation log (from `## Deviation log`); fixed + discarded findings with reasons; deferred commits if any (gate was closed); flagged deviations from grill decisions.

## Review machinery

Reviewer = fresh general-purpose subagent (never a fork - shared context = shared blind spots). Inputs: artifact path(s), package `decisions.md`, repo read access. Spec/plan reviewers return numbered findings: severity (HIGH/MEDIUM/LOW), problem, fix. Fail = any HIGH or MEDIUM. LOW-only = pass; append nits to `## Review nits`.

**Loop:** findings → revise artifact → re-review (changed sections focus; reviewer gets its own prior findings). Cap: initial + 2 re-reviews per artifact per resolution attempt. After round 2, only a HIGH finding buys another round; MEDIUM findings are fixed and recorded without re-review, LOW findings are appended to `## Review nits`. Marker numbering continues over the artifact's lifetime - the cap resets at gate resolution (case 7), the count does not. Still failing (HIGH) after the second re-review → abort: full report (stage, findings, history, paths, what resolving looks like). Artifacts stay on disk; recovery = user resolves, re-invokes, detection resumes.

**Reviewer checklists (embed in the spawn prompts):** Spec reviewer - internal consistency, no placeholders, faithful to the recorded decisions, single-plan scope, reads the codebase to verify factual claims. Plan reviewer - three axes: (a) plan-vs-codebase (file paths exist, structure claims match reality, task order respects dependencies), (b) plan-vs-design (every spec acceptance criterion covered, no invented scope, faithful to decisions), (c) plan-vs-reality (when the plan embeds test or implementation code that is self-contained and side-effect-free, execute it in a throwaway sandbox against its own fixtures - fail-open seams survive reading but not running; when the code is stateful, network-bound, or environment-dependent, hand-trace inputs through it instead and say in the findings which was done and why).

## Orchestrator-side escalation handling

On implementer return - **BLOCKER** (plan-level): apply the proposed revision to the plan file, re-run the plan reviewer on the changed sections (counts against the plan's cap-2), respawn the implementer from the checkpoint task. **SPEC-CONFLICT** (spec-level): abort the run - full report to the user (the contradiction, the implementer's evidence, artifact paths); spec and recorded decisions are user-owned, no autonomous path changes them.

## Implementer contract (in the spawn prompt)

You execute the plan file. You NEVER ask the user questions. Git authorization follows the user's global rules - the gate decides whether a commit lands. Plan "Commit" steps are logical per-task commits: if a commit is blocked (gate closed), record "commit deferred at task N - gate closed" in your deviation log and CONTINUE - the run never stops for git authorization. When the plan's requirements-update task cites a repo requirements contract, write the promised updates in the repo's own format per the requirements rules embedded in your prompt; never invent entries or reformat the contract. When all tasks complete, append `Implemented` to the plan footer. Blocked comes in three tiers:
- Implementation detail (naming, in-task structure): decide, log deviation + reasoning, continue.
- Plan-level (task wrong/missing/mis-ordered; in-task approach won't work): STOP. Return BLOCKER: task number, what reality shows, proposed plan revision. Do not fix the plan yourself.
- Spec-level (reality contradicts the spec or a D entry in the package `decisions.md`): STOP. Return SPEC-CONFLICT: the contradiction, evidence. Do not proceed.
Return: completion summary + full deviation log.

## Abort rules

Three abort triggers, all terminate with a full report - they never pause to ask mid-run: (1) review cap exceeded after the second re-review; (2) SPEC-CONFLICT (spec-level escalation - user-owned decisions); (3) subagent crash after one retry. Abort during interview stages: restart that stage from the top (human is present).

## Existing project documents

Use the global legacy-document rule before creating or resuming plans/backlogs: canonical `.agents` when present, legacy `.claude` when it is the only copy, reconcile both before resuming, editing, or migrating. Preserve IDs and checkbox progress.

## Contract mode

At the start of every stage - interview and autonomous alike - read the target
repo's AGENTS.md for a requirements-contract rule. Before the cycle's paths
are known that is the root file; once known, also the nearest nested AGENTS.md
governing those paths, nested-wins. Contract mode is on for a scope when its
AGENTS.md assigns update duties to a canonical requirements document and the
path is resolvable from the same AGENTS.md - in the rule text, or via a
definite reference ("the canonical requirements document") resolved by that
AGENTS.md's Documents map. A requirements-ish file with no rule is not a
contract. No rule -> off, cycle unchanged. Unresolvable path or multiple
candidate files in one scope -> off for that stage, one line in
`decisions.md` `## Contract mode`; never guess. A named file that does not
exist -> surface it, never invent entries. Detection re-runs each stage; duties
already recorded in the package stay durable even if the rule later
disappears - detection gates new filings only. When the topic names a
subproject, ask at grill which areas it touches and read that nested AGENTS.md
too - a nested-only rule is otherwise invisible before paths are known.

When on, load the requirements skill (it owns the contract's rules) and hold
the stage duties:

- Grill: file an R entry for every existing contract entry the topic touches -
  `Scope: amends <handle>` - extending the usual enumeration; statements
  verbatim when interpretation matters. Uncovered behavior: R entry
  `Scope: new`, and the implementing D entry names the contract addition in
  its Consequences.
- Test plan: each `amends <handle>` entry's verification pointer maps to at
  least one scenario; a pointer with no scenario is a recorded gap; a handle
  the contract lacks is a dangling-citation gap; an unclear pointer becomes
  a Q entry.
- Spec: cite the covered handles the spec depends on.
- Plan: when any R entry amends a handle or a D entry names a contract
  addition, the plan carries an explicit requirements-update task placed
  with or before the behavior change - never after it.
- Implement spawn prompt: embed the resolved contract path, citation
  convention, and duty checklist; subagents never re-detect on their own. A
  promised contract update whose plan task is missing is a BLOCKER.
- Code review spawn prompt: every promised update happened; every covered
  behavior change in the diff has an R entry or a recorded gap (coverage
  check); handles unique; each touched entry's verification procedure
  actually checks the entry.
- Verify-fix: a cycle with `amends` entries or a promised addition is not
  complete until each cited verification ran; results recorded in
  `decisions.md` `## Contract mode`. A failed or unrun verification is a
  review finding, triaged normally; a manual or planned pointer the
  autonomous zone cannot run goes to user disposition - at the launch gate
  when known there, else a review finding - never silently passed.

The launch gate summary includes contract-mode status and the
requirements-update task among the expected artifacts. All contract-mode
notes (ambiguity, skipped duties, verification results) go to
`## Contract mode` in `decisions.md` - the durable home.
