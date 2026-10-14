---
name: attack-claims
layer: worker
description: Use when the user wants a set of claims adversarially verified - "attack these claims", "try to disprove", "adversarially verify", "stress-test the claims in ..." - claims about documents, papers, datasets, code or results. Runs fresh attacker subagents per claim in waves, verdicts from the verify_claims oracle, ledger and survivor report on disk. Not auto-triggered - invoke via /attack-claims or an explicit request.
deps: [work-package]
---

# attack-claims

## Overview

Given a claim set - or text decomposed into one - run a branching adversarial
verification loop: a fresh-context attacker subagent per claim exploring
attack angles as research threads, then a fresh attacker wave for every
surviving claim until the wave cap, verdicts issued only by the best
available oracle, ending in a survivor report on disk.

Two modes. `attacker-gathered` (default): attackers gather their own
evidence - text, computation output, or found artifacts - via
refutation-seeking search and experiment. `verify-only`: claim sets that
arrive already span-cited get a single oracle pass, no attackers. The
oracle - the `verify_claims` MCP, the `verify-claims` CLI, or degraded a
separate judge subagent - is the sole arbiter; an attacker never self-grades.
The burden is refutation: an inconclusive attack does not kill a claim -
unrefuted claims survive, labeled. A claim survives only by withstanding
every wave; one supporting span never ends the attack.

## Setup

Runs once per run, before any attacker is dispatched; on resume it is
skipped and everything is read from the run header. Nothing is dispatched
before the user's go-ahead. Steps in order:

1. **Claims.** Input is either an explicit claim list, or text (draft,
   report, transcript) decomposed into atomic claims - one verifiable
   assertion per row, questions and lead-ins dropped (the oracle treats
   those as `non_claim`). Each claim names its subject material (document,
   paper, dataset, repo, URL) where the claim is about one.
2. **Mode.** `attacker-gathered` (default) or `verify-only`. Verify-only
   input uses the verifier's own contract: answer text with `[S#]`
   citations placed right after each claim, plus a spans list of
   `{"id", "text"}` or `{"id", "path", "start_line", "end_line", "ref"}`
   objects. Verify-only skips evidence hunting and makes a single oracle
   pass, batched at most 25 claims per call (the verifier's truncation
   cap). Every verify-only outcome is terminal - no waves, no attackers.
3. **Run directory.** Chosen per the Run directory and ledger section.
4. **Tier.** T1 by default. T2 only on explicit opt-in naming what it
   unlocks for this run - GPU/Slurm jobs, gateway spend, running
   third-party code; a T2 run also sets its own GPU-hour and spend caps.
   See Permission tiers and storage.
5. **Workspace.** A per-run directory outside the repo, default
   `${XDG_CACHE_HOME:-~/.cache}/attack-claims/<work-slug>/<topic>/`
   (standalone runs: `.../attack-claims/<work-slug>/`), tunable. It is
   persistent - the refutation audit re-runs scripts against it. Storage
   cap: default 20 GB per run and 5 GB per single download, tunable.
   Setup confirms the workspace filesystem has at least the cap free
   (`df`) and stops with a named shortfall if not.
6. **Oracle.** Detect the rung (Oracle ladder) and run its smoke call. An
   `oracle` option (`auto` default; `mcp`, `cli`, `judge`) forces a rung -
   for runs that must not touch the gateway.
7. **Budgets and deadline.** Set per Budgets and deadline.
8. **Confirm.** One message shows the claim list (decomposed lists are
   editable here), mode, tier and what it unlocks, workspace path and
   storage cap, oracle rung, budgets and deadline. On the user's go-ahead
   the run header and ledger rows are written and wave 1 is dispatched.

## Run directory and ledger

Load the work-package skill before creating the run directory - it owns
the `.agents/work/` layout.

Destination: an invoker directive naming the run directory wins; otherwise
the work-package layout decides. A run inside an existing work-package
(for example, attacking that work-package's spec) lands in
`attack-claims/<topic>/` inside it. A standalone run creates
`.agents/work/<date>-attack-claims-<topic>/`.

`attack-claims/<topic>/` holds `claims.md` (the ledger), `logs/` (attacker
logs and the scripts behind computational evidence) and `report.md`.
Distinct topics never collide; a rerun on the same topic resumes it.
Standalone runs place the three at the run directory's root, not nested
under a topic directory. Bulky material lives in the workspace, never
here. No state line.

Run header (top of `claims.md`, written at the end of setup; the resume
source for everything a run needs):

```markdown
mode: attacker-gathered | tier: T1 | oracle: mcp |
workspace: ~/.cache/attack-claims/2026-10-14-attack-claims-foo | storage: 20 GB run,
5 GB per download | started: 2026-10-14T10:02Z |
deadline: 2026-10-14T14:02Z | budgets: waves 3, calls/claim/wave 8,
calls/run 200 | calls used: 37 | storage used: 3.1 GB
```

Row format (one per claim):

```markdown
- C1. <claim text> | mode: attacker-gathered | spans: <ids or none> |
  wave: 2 | status: passed | attempts: 2 | verdicts: w1:passed, w2:passed |
  budget: 6 calls, 2 waves | notes: steelman S3; no counter-evidence
```

Statuses, terminal: `contradicted`, `disputed`, `unverifiable (searched)`,
`unverifiable (budget exhausted)`, `unverifiable (storage cap)`,
`unverifiable (time limit)`, `unverifiable (attacker failed)`,
`unverifiable (oracle error)`; `passed` - at once in verify-only mode, at
the wave cap in attacker-gathered mode; verify-only only: `not_entailed`,
`uncited`, `unknown_citations`.

Non-terminal: `pending` (never dispatched), `attacking` (dispatched, wave
in flight), or a standing verdict - `passed` or `not_entailed`,
attacker-gathered mode, between waves. A standing verdict becomes
terminal at refutation, the wave cap, or exhaustion. `wave: n` counts
completed waves; a dispatched row shows `attacking` until it returns. Run
state = whether every row is terminal. Rows carry `degraded` in notes when
their verdict came from the LLM-judge rung. `attempts` counts attacker
dispatches (retries included) so the one-retry rule survives compaction.

The orchestrating session is the sole ledger writer. Attackers return
verdicts in their replies and write only their own log file
`logs/C<n>-w<m>.md` (plus scripts under `logs/C<n>-w<m>/`) and files
inside the workspace.

Resume: re-read header and ledger, re-key on row status - every
non-terminal row (`pending`, `attacking`, or a standing verdict)
re-dispatches for wave `n+1` of its `wave: n`; terminal rows never re-run,
except an `unverifiable (oracle error)` row the user asks to re-attack
after a rung drop, which resets to `pending`, recorded in notes. Tier,
workspace, budgets, deadline and oracle rung come from the header. One
orchestrating session per work-package.

## Permission tiers and storage

Attackers get full tools, bounded by blast radius:

| Tier | Allowed |
|---|---|
| T1 (default) | Read, search, fetch; write and run its own scripts (CPU, local process) with packages via `uv run --with`; downloads, data copies, clones and throwaway worktrees inside the workspace |
| T2 (opt-in) | T1 plus what setup unlocked for this run: GPU/Slurm jobs, gateway spend, running third-party code (cloned repos, paper code) - each within its setup cap |
| Never | Mutating the user's working tree, remotes, shared services, global environment, or anything outside the workspace and the attacker's own log paths |

Subject material the attack needs (a dataset, a repo) is copied or cloned
into the workspace; originals are never touched. Throwaway worktrees are
created only under `<workspace>/worktrees/`, so `git worktree list`
filtered by that prefix finds every one - including after an interrupted
run.

Storage discipline: before any download the attacker learns its size
(HEAD `Content-Length`, API size metadata) or streams it with a hard cap
(`curl --max-filesize`); a download larger than the per-download cap or
the remaining run storage is not started - the angle is noted as blocked
by storage. After writing large outputs it checks `du -s` of the
workspace.

Storage enforcement: the orchestrating session checks `du -s` of the
workspace before every dispatch and on every attacker return and updates
`storage used` in the header. At or over the run cap nothing new is
dispatched; rows not terminal once in-flight attackers return become
`unverifiable (storage cap)`. Enforcement is protocol-level (attacker
pre-download checks plus these checks), not a filesystem quota.

## Waves

Each attacker is a fresh-context subagent, briefed to disprove its claim,
not to review it. The orchestrating session fills the brace placeholders
in `attacker-brief.md` - the claim, its subject material, prior waves'
angles and verdicts, the tier and its allowed-actions line, the workspace
path and remaining storage, the run deadline, the oracle rung and its
call form, and the per-wave oracle invocation budget - and passes it
verbatim as the subagent prompt.

Waves run breadth-first: every live claim finishes wave n before any
claim starts wave n+1, at most 6 attackers in flight. Every non-terminal
row gets the next wave - a fresh attacker at angles prior waves did not
cover - including rows standing at `passed`; one supporting span never
ends the attack. At the wave cap (default 3 waves) a standing `passed`
becomes terminal `passed`; a standing `not_entailed` becomes
`unverifiable (searched)`.

`attempts` counts attacker dispatches, retries included; a crashed
attacker or a missing log gets one retry with the same brief (Errors).
Where the harness cannot spawn subagents (opencode), the attacker runs
sequentially inline in this session - one claim at a time - and the
brief's protocol applies unchanged.

## Refutation audit

Before recording `contradicted` or `disputed`, the orchestrating session
audits the refutation:

- Text and existence spans: re-read each refuting span from its source
  (file at `ref`, or a re-fetch of the URL) and confirm the quote is
  verbatim.
- Computational spans: re-run the logged script with the logged command
  in the workspace and confirm the output reproduces the quoted excerpt;
  read the script and confirm it tests the claim as stated, not a weaker
  variant.
- Negation route: confirm the negation states the opposite of the claim
  and nothing weaker.

A failed audit discards the refutation and the row continues as if it
had not been found, with the failure in notes. Computational evidence
that does not reproduce is a failed audit, non-reproduction noted.

## Verdicts

Per wave (attacker-gathered):

- Refuted on either route, audit passed -> `contradicted`, terminal.
- The claim and its negation both entailed -> `disputed`, terminal; the
  report shows both span sets. When one span entails both, the note says
  so - an ambiguous claim or an inconsistent span.
- Claim entailed, no refutation -> standing `passed`.
- Neither -> standing `not_entailed`, with the optional
  `suspected-contradiction` annotation (the oracle's `contradicted` is
  conservative).

Verify-only is a single oracle pass, no waves; every outcome is terminal
and `passed` holds at once. `not_entailed` is mode-dependent: terminal in
verify-only mode (the claim fails its own citations - it does not stand on
its evidence); in attacker-gathered mode a standing verdict resolved at
the wave cap. `uncited` and `unknown_citations` are verdicts only in
verify-only mode, where the report presents both as the claim not standing
on its evidence; in attacker-gathered mode they mark a malformed
submission (Errors). `non_claim` from a decomposed or verify-only claim is
an intake defect: rewrite the claim as an assertion or drop it with a note
in the report - never silently. Verifier statuses outside the report
taxonomy (`prior_leak`, `insufficient_evidence_gain`) map to standing
`not_entailed` for that wave, the status named in notes; the wave cap
resolves the row as usual.

## Oracle ladder

The rung is chosen once at setup and recorded in the header:

1. `verify_claims` MCP when present - subagents inherit it.
2. Else the `verify-claims` CLI via Bash: resolved by
   `command -v verify-claims`, then the known deploy path
   `/mnt/data/slurm_llm/bin/verify-claims`; reachable when a one-claim
   smoke call exits 0 or 1 (exit 2 = call or config error). Invocation:
   `verify-claims <answer-file> <spans-file>`; exit 0 = passed, 1 =
   flagged, 2 = error. The answer file holds the claim sentences with
   `[S#]` citations; the spans file is a JSON list of span objects.
3. Else a degraded LLM-judge: a separate fresh-context judge subagent -
   never the attacker - receives only the claim and its spans and emits
   the same verdict schema; its brief is filled from `judge-brief.md`.
   The report is stamped `degraded - LLM-judged, not oracle-judged`. In
   sequential-inline harnesses the judge runs as a separate inline pass,
   and the stamp also says `same-session judge`.

A rung drops mid-run after 3 failed oracle invocations across the run -
an invocation that, after its one retry, still returns `internal_error`
(call-level) or `verifier_error` on any claim - whatever claims they hit.
The header records the switch and later claims use the new rung. Rows
already terminalized `unverifiable (oracle error)` stay terminal; on the
user's request the orchestrating session resets such a row to `pending`
(the one exception to terminal rows never re-running), recorded in notes.

## Budgets and deadline

Budget unit: one oracle invocation - one `verify_claims` MCP call, one
CLI run, or one judge pass - whatever its claim count. Attackers report
their invocation count in each reply; the orchestrating session adds it
to the row's budget and to `calls used` in the header on every return.
The report also totals the gateway calls from each verdict's
`summary.verifier_calls`.

Defaults, all tunable at setup: max 3 waves per claim; 8 oracle
invocations per claim per wave; global cap of 200 per run; storage 20 GB
per run, 5 GB per download; run deadline 4 h after dispatch starts. A run
with `unlimited` effort requires the deadline to be confirmed explicitly
at setup; `unlimited` lifts the effort caps - waves, per-wave calls, and
the global calls cap - leaving the run's wall-clock deadline as the only
effort terminator, while the storage cap and any T2 caps still apply. Rows
that exhaust any budget are labeled with the specific exhaustion reason.

Calls enforcement: the orchestrating session checks `calls used` against
the global cap before every dispatch and on every attacker return. At or
over the cap nothing new is dispatched; rows not terminal once in-flight
attackers return become `unverifiable (budget exhausted)`. In-flight
attackers may overshoot the cap by up to the concurrency width; their
returned verdicts are still recorded.

Deadline enforcement: subagents cannot be interrupted, so the deadline is
checked before every dispatch and on every attacker return, and attackers
check it themselves. After the deadline nothing new is dispatched;
verdicts returned late are still recorded; rows not terminal once the last
attacker returns become `unverifiable (time limit)`.

## Errors

- Attacker crash or missing log: one retry with the same brief; second
  failure labels the row `unverifiable (attacker failed)` and the run
  continues. Retries consume budget like any attempt.
- Oracle input errors (`invalid_span`, `no_spans`, `invalid_answer`,
  `duplicate_span_id`, 200-line span cap) and malformed submissions in
  attacker-gathered mode (`uncited`, `unknown_citations`, `non_claim` on
  the attacker's own answer): the attacker repairs its answer or spans
  and resubmits; persistent failure consumes budget like any attempt.
- `truncated`: never sent - every call carries at most 25 claims.
- `verifier_error` / `internal_error`: retry the invocation once;
  persistent failure labels the affected rows
  `unverifiable (oracle error)` - the claims carrying `verifier_error`,
  or every claim in the call for call-level `internal_error` - and the
  rung-drop rule applies.
- `ambiguous_verifier`: an identical resubmission is futile (temperature
  0 plus a process-local cache return the byte-identical verdict), so
  retry only with changed input - repaired or renumbered spans; otherwise
  neither entailed nor refuted - standing `not_entailed` with the
  ambiguity noted (attacker-gathered), or under Failed own evidence with
  the ambiguity noted (verify-only).
- Computational evidence that does not reproduce on audit: refutation
  discarded, non-reproduction noted.
- Download size unknown and uncappable: not started; the angle is noted
  as blocked by storage.
- Setup failures (workspace filesystem below the storage cap, no writable
  workspace): stop before dispatch, naming the shortfall.
- Time limit and storage cap: enforcement per Budgets and deadline.
- No oracle rung available (no MCP, no CLI): the run proceeds degraded
  and the report header says so; never silently pretend oracle verdicts.

## Report and teardown

The report is written to `report.md` in the run directory and summarized
in chat. Header: mode, tier, oracle rung (and any degradation stamp),
budgets, calls used, storage used, wall-clock. Sections in order:

1. Survived - `passed` (entailed and unrefuted across all waves), then
   `unverifiable (searched)` (unrefuted, but no entailing evidence found -
   survives under the burden-of-refutation rule, labeled).
2. Refuted - `contradicted`, each with its audited refuting spans
   (attacker-gathered runs; verify-only `contradicted` rows carry the
   caller's spans unaudited - no attacker log exists).
3. Disputed - both span sets.
4. Failed own evidence (verify-only) - `not_entailed`, `uncited`,
   `unknown_citations`.
5. Unfinished - `unverifiable (budget exhausted | storage cap | time
   limit | attacker failed | oracle error)`: never attacked to
   completion, so neither survived nor refuted.

Every intake claim appears exactly once, plus any dropped `non_claim` with
its note.

Teardown: a run that ends without a report is interrupted - nothing is
deleted, and its worktrees stay findable under `<workspace>/worktrees/`.
Any run that writes a report - including one whose report contains
Unfinished rows - tears down: the orchestrating session removes the run's
throwaway worktrees and asks the user before deleting the workspace (its
outputs back the computational evidence; re-auditing needs them). A
resumed interrupted run skips teardown until its own report is written.
