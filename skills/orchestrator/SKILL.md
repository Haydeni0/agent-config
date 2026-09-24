---
name: orchestrator
description: Use when the user delegates a queue of several independent units to run over subagents - a plan or decisions file naming multiple units, a request to run them autonomously over a long unattended stretch, or a multi-unit queue already in flight after compaction or a dead session. Units may be builds, investigations, or other kinds. Not for single-unit work, where dev-cycle alone suffices.
---

# orchestrator

## Overview

Run a queue of independent units over an unattended stretch. A unit is a self-contained deliverable with a verifiable done-condition. One unit = one isolated workspace, built by a subagent with a front-loaded brief, verified by the orchestrator, reviewed by a separate clean-context subagent where the deliverable is reviewable, and delivered through its transport. The orchestrator's context window is the scarce resource: reserved for gates, verification, delivery, and decisions. Everything delegable is delegated.

The main session is the only interface to the user. Subagents report to it and never produce user-facing output. Escalation reaches the user only for outcomes and decisions a human must make; progress, retries, and internal mechanics are batched into the next natural report.

Earned by repetition: this pattern ran a multi-unit queue end to end with units shipped, merged, and recovered mid-flight. For a single unit or one-off work, skip this skill and run the unit's executor directly.

Baseline assumptions: the harness supports subagent dispatch and isolated workspaces (git worktrees for anything touching a repo), and the user's skill set - grill-me, dev-cycle, backlog - is installed and syncs across the user's harnesses; where one is genuinely absent, run the shape its step describes inline. Other harness-specific mechanisms (resuming a named subagent, background completion notifications) are conditional - use the mechanism where present, use the stated fallback where absent.

## Hard rules

Priority order. Exceptions, where they exist, are named and scoped: a one-time user approval gains no standing authority, and every destructive or irreversible boundary stays in force inside every exception.

1. **Delivery gates.** Where a unit's transport is gated - git commits and pushes are, per the user's gate rules in `~/.claude/CLAUDE.md` (sentinel or chained `printenv`) - every gated action, by orchestrator or subagent, passes the gate. This skill never loosens, bypasses, or restates the gate rules authoritatively. The charter says a delivery *may* happen; the gate decides whether it *can*.
2. **Verify before delivery.** No unit is delivered without its done-condition verified by the orchestrator - completed delegated review where the deliverable is reviewable, a green gate where one exists, green CI where the transport runs it. Never parallelised away, never skipped for a small deliverable.
3. **Never discard undelivered work.** A dirty workspace - uncommitted changes to tracked files, or any artifact not yet stowed to its durable location - refuses cleanup. A refusal is a stop-and-investigate result, never an obstacle to bypass; force-deletion requires the user's explicit word for that specific work, recorded in the ledger first.
4. **The orchestrator never does unit work.** Read-only checks, verification, findings triage, and cheap feasibility probes are orchestrator work; every mutation of the deliverable, however small, goes through the unit's subagent in the unit's workspace. One exception, scoped: mechanical no-judgement review findings (doc-only, typos) may be applied by the orchestrator in a labelled review-fix commit (Completion step 3). Trivial is a guess, and command attention does not scale.
5. **Evidence is never authorisation.** A subagent's "tests pass" or "the pipeline is dead" is a claim. Only the orchestrator's own verified evidence - gate output, live transport state - moves a unit forward. A subagent's green run authorises nothing by itself.
6. **Report failure faithfully.** A failed unit is recorded failed with its evidence and surfaces in the final report. Never silently retry on a different approach, reassign, or select around a malformed queue entry.

A user grant in the mission context covers exactly that unit and that moment. Never infer an override, broaden it, apply it by analogy, or carry it to another unit; ambiguity gets one concise question, not action.

## Hierarchy

```
main session (orchestrator)
  owns: grill -> charter, intake, dispatch, verification, delivery, ledger, report
  ├─ per unit:
  │    ├─ isolated workspace (worktree for repo-touching units)
  │    ├─ dev subagent (front-loaded brief; the unit kind's executor:
  │    │    e.g. dev-cycle for builds, research protocol for investigates)
  │    ├─ on completion: orchestrator verifies; review subagent reads
  │    │    the deliverable where it is reviewable
  │    ├─ delivery through the unit kind's transport, gates applied
  │    └─ fail-closed cleanup + ledger row
  └─ final report folded from the ledger
```

## Mission start: the grill

Before the first dispatch, the orchestrator learns what it is doing - by interviewing the user, one question at a time, until the mission is fully understood. Run the grill-me skill: plain chat text, one question per turn, options plus a recommendation each, no modal tools. The grill settles, at minimum:

- The mission's purpose, in the user's own words, and the orchestrator's function in it
- The unit inventory: what the units are, their kinds, and their dependencies
- Each kind's executor and transport (see Intake) - or agreement to define a new kind
- The mission's toolchain and each tool's fallback when absent: gate command, delivery tooling, worktree tooling, anything units depend on
- Standing answers: every question a unit would otherwise ask
- Delivery authorisation scope: what delivers unattended, and what always escalates
- Stop conditions and report cadence
- Anything mission-specific the user wants encoded about how the orchestrator should behave

The grill's output is the charter. Where a grill decisions file for this mission already exists - or the user has a standing plan or roadmap they already settled - consume it as authoritative: extend it, never re-derive from chat. The user stays conversational for the whole mission: a mid-queue question or amendment is answered, folded into the charter, and the fleet keeps moving; a substantial re-scoping reruns a short grill round.

## Autonomy

Three tiers govern mid-flight judgement. Where the repo's AGENTS.md defines its own autonomy tiers, the repo wins.

| Tier | Trigger | Action |
|------|---------|--------|
| Decide and note | Routine judgement - naming, layout, a fixture's shape | Do it. One line in the commit body or ledger |
| Queue | A genuine fork, but unblocked work remains | Record to `.agents/backlog.md` via the backlog skill, continue |
| Stop | Nothing meaningful unblocked; irreversible, destructive, or outward-facing action outside the charter's delivery scope; a fork only the user can make | Halt that unit, report |

Subagents get the same tiers in their brief; decide-and-note decisions surface via their deviation log. Plan-level wrongness returns BLOCKER; spec-level contradiction returns SPEC-CONFLICT. A subagent asking a question mid-flight is not a supported channel - it returns blocked with the question, and the orchestrator answers, holds it in the ledger, or escalates.

Delivery actions the charter pre-authorises do not count as Stop-tier outward-facing actions; the always-escalate list in Delivery (force push, destructive or security-sensitive merges) is never waived by charter, AGENTS.md, or grant.

## The charter

Written to `.agents/plans/<date>-<mission>-decisions.md` in the repo (for a grilled mission, the grill decisions file is the charter); for a repo-less mission, a mission directory on disk serves. It holds: the mission goals verbatim, the unit list as an advisory starting plan with kinds and dependencies, standing answers, delivery authorisation scope, stop conditions, report cadence, and the ledger. The orchestrator re-plans waves as units land - adding, splitting, or deprioritising units within charter scope, without re-asking. Multi-repo missions are allowed - the charter lives in the lead repo, and unit state lives in each unit's workspace; typically one repo.

### Ledger

Append-only, in a dedicated section at the end of the charter file - so the grill's settled decisions above it stay a clean consume-as-authoritative artifact. One row per unit event, holding what the workspace cannot recover: dispatch record (base state and worktree path), deliverable references copied verbatim (PR URLs, stowed report paths), verification verdicts, delivery results and confirmations, attempt counts, and ruling lines in the form `Ruling: <what> - <why> - <cost if wrong>`. Outcome rows are appended after the outcome is observed, never before; the dispatch record (base state and worktree path) is written before dispatch. Meaningful absence: no ledger row means the unit was never dispatched; an empty deliverable field means not yet delivered. Shape, concretely:

```
- mesh-solver: dispatched base=1b73214 worktree=.claude/worktrees/mesh-solver
- mesh-solver: verified gate green; review clean
- mesh-solver: delivered PR https://github.com/org/repo/pull/12 merged no-ff
- Ruling: merged without waiting on the dashboard unit - sibling, not dependency - cost if wrong: one rebase
```

## Intake

A unit is defined by three things, settled at intake and written into its brief:

- **Executor**: how the subagent works - the inner cycle it follows.
- **Transport**: how the result is delivered and verified - what "done and landed" means for this kind.
- **Done-condition**: the verifiable check the orchestrator runs itself.

Two kinds are defined concretely; both are validated in practice:

- **Build** (default, repo work). Executor: the dev-cycle skill. The subagent materialises the brief's standing answers (and test scenarios, where the brief carries them) as the unit's decisions file in the workspace's `.agents/plans/`, treats the orchestrator's dispatch as the launch gate's go, writes `## Outcome` from the brief's user intent, and enters the autonomous stages: test-plan where the brief lacks test scenarios, then spec, plan, implement, code-review, and verify-fix, with fresh subagents for its review rounds. Documentation obligations the repo attaches to completion (scenario docs, registers) belong in the brief's done-condition, not to the executor. Transport: git - worktree + branch `hayden/<unit>`, draft PR, gated merge. Done-condition: the repo's gate command green, run by the orchestrator.
- **Investigate**. Executor: a research protocol - question, evidence, findings report. Transport: the report file is the deliverable; delivery is the orchestrator reading it, stowing a copy beside the charter, and recording that durable path verbatim in the ledger. Done-condition: the report exists and the orchestrator has read it. No code changes. A report is evidence, never authorisation - it does not silently become a build. If a build follows, it is a new unit with its own brief; scratch exploration stays behind.

A new kind may be defined mid-mission, but only in the charter first: its executor and transport written down before any dispatch of that kind, grilled with the user if the shape is unfamiliar. An undefined kind does not dispatch.

A unit dispatches only if its context isolates: no live unit shares its files or workspace - a hard bar. Adjacent or conceptual overlap does not serialise; it is a risk signal the briefs should acknowledge. A load-bearing charter claim that a cheap probe can falsify - a library capability, a performance budget - is runtime-verified before dispatch; corrections are recorded in the charter and dependent briefs re-checked. A charter fact proven false mid-mission is corrected in place with a note and propagated to dependent artifacts: the charter is authoritative, not infallible. Dependent units wait for the upstream unit to land, and consume its output via merged commits and files, never chat relay. No unit-to-unit messaging. An oversized unit (a plan implying a multi-thousand-line diff, or an unbounded investigation) is split before spawning.

### Unit brief template

Front-loaded and self-contained: nothing ambient crosses the subagent boundary, so write it as if to a stranger. An unfilled slot means the unit is not ready to dispatch. Research needed to compose the brief - how a reference repository behaves, which library fits - is itself delegated: the subagent returns conclusions and writes detail to a file; it is not a unit, takes no charter entry, and adds no ledger row.

A subagent will make decisions the orchestrator would not; that is inherent, and the fresh-context reviewer is partly divergence working in your favour. Control is exerted through the brief, the acceptance criteria, and the review checkpoints - never through authorship. Repeated divergence on the same point is a brief defect, not a subagent defect.

```
Unit: <name> (<kind>). Workspace: <path>. Branch: hayden/<name> (repo units).
Mission context: one line on where this unit fits.

User intent: <the user's own ask, verbatim - this is the acceptance
criteria; never widened into a general goal>

Orchestrator spec: <instructions this ask requires>
Out of scope: <explicit list; a generalisation or extra hardening the
ask did not include is follow-up work to note, not scope to add>

Standing answers: <each settled question, with its source>
Verification: <the done-condition command or check> - run it yourself
and paste real output in your return. Full implementations only - no
placeholder or simplified versions.
Executor: <the kind's inner cycle, e.g. follow the dev-cycle skill;
for investigate: the research protocol and the report file to write>
Repo rules that must reach you: <restate verbatim only what the worker
must obey - requirement-citation rules, test style, GPU pinning>
Git: commits and pushes follow the user's global gate rules (<restate
the gate mechanism from ~/.claude/CLAUDE.md>); if a commit is blocked,
record it deferred and continue.

Autonomy: <three tiers, or pointer to repo AGENTS.md>. Log deviations
with reasoning. Use your executor's own escalation machinery where it
has one (dev-cycle resolves plan-level revisions internally); return
BLOCKER only where that machinery aborts, and SPEC-CONFLICT for any
spec-level contradiction. Do not ask questions mid-flight; if truly
blocked, return blocked with the question.

Isolation check, before anything else: verify your working directory is
the workspace above and the branch is as assigned. If not, stop and
return blocked.

You never review or grade your own work; review happens in a fresh
context outside this one.

Return contract: status (done | done-with-concerns | blocked), commit
range or deliverable path, one-line evidence, concerns. Full detail
goes to a report file in the workspace; return its path. When the
transport carries a URL, end with a line the orchestrator can grep:
UNIT <name> <status>: <full url>.
```

Cross-unit interface facts and the orchestrator's ruling on any known ambiguity are pasted in full - never summarised away; actions carry implicit decisions.

## Dispatch

1. **Spin up.** Repo-touching units get a worktree, branch `hayden/<unit>` from the mission's base. Prefer `wt switch --create hayden/<unit> --no-cd --no-hooks` when the wt CLI is available - the worktree lives at wt's configured location (`--no-cd` keeps the orchestrator's own directory put; `wt remove` later does merge-aware branch cleanup); else `git worktree add <repo>/.claude/worktrees/<unit> -b hayden/<unit>`. Record the worktree path in the ledger either way. Run the repo's workspace setup (dependency install) before spawning if the repo needs it. Exclude the worktrees location from the main checkout's lint and format gates - a main-checkout auto-fix pass can rewrite a subagent's mid-flight work. wt operations are orchestrator-owned; subagents get paths, never wt commands. Non-repo units get an equivalent isolated directory.
2. **Record the base state** in the ledger before dispatch (for repo units, the base SHA). Review diffs are always `base..head`, never `HEAD~1`.
3. **Dispatch one subagent per unit** with the brief. For a mission whose units are a new shape, run the first unit alone and read its return before fanning out the rest.
4. **Parallel by default.** Independent units dispatch concurrently with no orchestrator-imposed cap; the harness's own concurrency limit is the only mechanical bound. Serialisation requires a named concrete condition: a true semantic dependency, shared mutable external state, or an incompatible concurrent migration. Device-measuring units stagger or run CPU-side to avoid GPU contention. Sibling units racing a shared first (a landing-order claim in a register) resolve it by merge order - whoever merges first holds it; briefs hedge the claim as candidate until landed. The orchestrator owns merge-conflict resolution on shared registration files; units never rebase onto each other mid-flight.

## Supervision

Between waves, run cheap deterministic checks (git log per unit, live transport state) - spend a subagent or a user-visible turn only on real state transitions. Where the harness notifies completion natively, trust the notification - only re-probe on a confirmed error, never on absence of a notification; where the harness does not notify natively, the between-wave checks are the supervision.

- **Positive evidence only.** A quiet unit counts as progressing only with proof: fresh commits on its branch, writes in its workspace, or harness liveness. Silence plus no evidence means surface the unit.
- **Unknown is never promoted.** A unit moves to done or delivered only on verified evidence; unverifiable state blocks the wave until inspected - never silently classed as working or finished.
- **Dead-run detection.** All evidence channels empty - no new commits across three supervision passes, no workspace writes, and no harness liveness signal where the harness provides one - means the unit is stuck: run the recovery ladder. A live liveness signal defers the ladder, however quiet the unit; where no liveness channel exists, weigh elapsed silence against the unit's plausible runtime before calling it stuck. Slowness alone is not stuck.
- **End of turn.** Never end a turn with a unit in flight without its next expected event recorded and the ledger reflecting reality. Where the harness supports queuing the orchestrator's own next turn, at most one self-follow-up per turn.
- **Reconcile recorded units only.** No discovery sweeps of stray worktrees or branches, no adopting unrecorded work, no self-directed tidying. An empty queue invents no work.

## Completion

1. **The orchestrator runs the done-condition itself** - in the unit's workspace for repo gates, by reading the deliverable for investigate units - and reads the output. A subagent's pasted output is corroboration, not the verification.
2. **Review is delegated** where the deliverable is reviewable - a build diff always; an investigate report only when the charter asks for one - to one clean-context review subagent. It receives the deliverable (the diff, `base..head`, or the live PR head once a PR exists - fetch it; a recorded SHA is a pointer, never authority), the user intent and acceptance criteria, the unit's decisions and spec artifacts and the subagent's deviation log where they exist, and a precise brief of what the orchestrator has already verified and how - a reviewer disagreeing with a verified fact escalates it with evidence rather than silently acting on it. It reports gaps, not style preferences, bounded to correctness and the stated requirements. It never sees the dev transcript, and it never edits anything. The executor's own internal review is part of the unit's build; this step is the independent gate on the finished deliverable - the one-review-owner rule below bounds this step, not the executor's cycle. Exactly one review owner per unit - extra rigour means re-reviewing the fix diff with expanded criteria, never stacking a second reviewer on an already-reviewed deliverable.
3. **Findings route by context-need.** Mechanical, no-judgement findings - doc-only fixes, typos, renamed references - are applied by the orchestrator directly in a labelled review-fix commit, re-review scoped to that commit; the test is whether a fix requires reading the unit's hard-won context, and one that does not never needs the unit's agent. Everything else goes back verbatim to the unit's subagent - resume it where the harness supports that, else respawn with the brief plus the findings - which triages them against its brief, fixing what the accepted intent requires, refusing reviewer-authorised scope growth, and re-running its verification. Re-review is scoped to the fix.
4. **The orchestrator reads only the conflicted shared-contract files that conflict prediction names**, where a merge decision needs first-hand judgement: `git merge-tree --write-tree <base> <branch>` is read-only and names conflicted files before they are real. Run it before every merge.
5. **A mid-flight scope change is a new unit**, not extra scope in a running unit - except total invalidation (restarts the unit) and minimal fixes keeping already-accepted intent correct (stay).

## Delivery (build transport)

For build units. Delivery tooling, if any, is settled at the grill and named in the charter - run it when healthy, and fall back to the verify-then-merge sequence below when it is absent or unhealthy. A driving tool that blocks gets a bounded wait with a reattach loop, never an unbounded call that hangs the turn. Merge to main is pre-authorised only per the charter's scope; the git gates stay mechanical on top. The merge method is explicit, `--no-ff` by default unless repo convention says otherwise.

Verify-then-merge, in one command sequence:
1. The unit's subagent opens the draft PR as part of implementation; delivery marks it ready first - a draft is a named refusal condition at merge time.
2. Run conflict prediction and read any conflicted shared-contract files it names (Completion step 4); then one live read immediately before merging: PR open, not a draft, mergeable, conflict-free, every check green at the current head. Recorded metadata never substitutes for this read; a rebase or base advance invalidates it.
3. Merge pinned to the verified head, method passed explicitly.
4. Re-read after the command returns to confirm the landing. Never report success from the exit code alone.
5. Append the ledger row (merge result, PR URL verbatim).
6. **Fail-closed cleanup, any kind:** landing confirmed; the unit's report stowed beside the charter with that durable path recorded in the ledger, and the workspace copy deleted; no uncommitted changes to tracked files; then the kind's removal command - `wt remove`, `git worktree remove` + branch delete, or the equivalent for non-repo workspaces. Any residue or refusal is a finding for the user, never an obstacle to force.

A failing check never silently merges. If the user says merge anyway, they name the exact single check waived; every other gate stays enforced. Force push, and destructive or security-sensitive merges, always escalate regardless of standing autonomy. Other transports carry their own verify-then-deliver sequence, defined with the kind in the charter.

## Recovery

State lives in the unit's workspace. A dead or compacted-away subagent loses nothing that matters: workspace git state (or the deliverable files) plus the report files are the full state. The ladder, in order:

1. Read the subagent's return or transcript for a question the brief already answers; where the harness supports resuming, resume it with a one-line answer or correction.
2. Else respawn a fresh subagent into the **same** workspace and branch, with the brief re-sent verbatim plus a concise progress note derived from the recorded state ("work so far: X, resume from Y"). Never a fresh workspace while the recorded one is unaccounted for - that splits one unit across two copies.
3. After a second failed recovery attempt (resume or respawn), mark the unit failed in the ledger with the failure stated plainly, keep the workspace for the user, and continue the queue.

Never relaunch on ambiguous liveness - a unit that may still be running is left alone, to avoid duplicate workers on one branch. Record a death once; do not re-alarm on every pass. Repeated failure on the same obstacle is a signal the brief or spec is wrong: fix the brief, not the code, before the next dispatch. The failed record stays failed in the ledger and report; the brief fix is a recorded ruling and the re-dispatch a fresh, visible decision - never a silent retry.

## State and compaction

Disk is authoritative; conversation memory is not. No unit state, deliverable reference, decision, or verdict exists only in conversation. Open every session and turn by re-reading the charter and ledger and reconciling against live repo and transport state before acting - status records are history; current state is re-derived from the world, never from the last line alone.

Before any context reset or when context runs low, stow first: write any not-yet-recorded facts (open PR numbers, verification verdicts, chat-given answers, next steps) into the ledger and unit report files. If reconstruction of the queue's state from disk is impossible, something was not stowed.

## Final report

Folded from the ledger, so it survives any number of compactions. It stands alone - the user may read only this message. In outcomes, not mechanics; translate internal nouns (worktree becomes "local copy", teardown becomes "cleanup"). Contents:

- What landed: per unit, outcome + deliverable references copied verbatim from ledger rows
- Verification and CI state per unit, with evidence
- Decisions taken (rulings from the ledger), refutations, concerns from done-with-concerns units, and failed or blocked units stated plainly with their evidence
- Open user-owned decisions and backlog items raised
- An explicit "not safe to walk away" call when anything remains unverified
- A one-line resume pointer naming the charter and ledger

Proposed lessons (repeated failures, brief defects, patterns worth a rule) are listed as proposals for the user to accept into CLAUDE.md, AGENTS.md, or this skill - the orchestrator never edits standing rules itself.

## Rationalisation table

| Excuse | Reality |
|--------|---------|
| "I'll just review this diff inline to be thorough" | Inline review burned ~100k tokens of orchestrator context on one unit. Delegate; read findings |
| "The subagent reported tests pass" | A claim. The orchestrator runs the done-condition itself |
| "Unit looks done, mark it delivered" | Unknown is never promoted. Verify landed and green first-hand |
| "Merge command exited 0" | Confirm the landing after. Exit codes lie |
| "Dirty worktree blocks cleanup, force it" | Refusal is a finding. Discard needs the user's word, recorded first |
| "Small fix, faster to do it myself" | Unit work goes to the unit's subagent; only mechanical review-fix findings land inline, in a labelled commit |
| "One approval covers the rest of the queue" | Grants are concrete and scoped to one unit and moment |
| "Re-dispatch the failed unit with a tweaked approach" | Silent fallback is forbidden. Failed = failed, with evidence, in the report |
| "Helpfully sweep those stray worktrees" | Reconcile recorded units only. Empty queues invent no work |
| "The ledger says it shipped" | Recorded metadata is a pointer, never authority. Live-read it |

## Provenance

Validated in practice: workspace-per-unit, front-loaded briefs, one subagent per unit, delegated review, orchestrator-run verification, merge-tree conflict prediction, git-gated delivery, parallel waves, recovery from workspace state, mission decisions file, final report shape.

Grafted from research (prune freely if a graft misfires): harness-agnostic conditional clauses, hard-rules opening with anti-carry clauses, append-only ledger, base-state discipline, investigate unit shape, verify-then-merge, waived-check naming, fail-closed teardown, recovery ladder order, positive-evidence supervision, unknown-never-promoted, escalation batching, end-of-turn checklist, stow ritual, report-from-records, brief-defect steering rule, proposed-lessons governance.

Every rule here traces to a real failure or a documented one; when updating this file, preserve the safety boundaries and prefer rewriting over appending.

## Existing project documents

Use canonical `.agents` plans when present and legacy `.claude` plans when they are the only copy. When both exist, reconcile before resuming, editing, or migrating; preserve checkbox progress and backlog IDs.
