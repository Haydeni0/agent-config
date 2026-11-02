---
name: work-package
layer: worker
description: Use when reading, writing, or resuming work in a `.agents/work/<slug>/` package, or when another skill cites this contract. Holds the on-disk contract - package layout, slug convention, file roles, entry formats, ID rules, marker formats, the state line, and the legacy conversion recipe. Load it before reading or writing package files.
---

# work-package

Reference contract for `.agents/work/<slug>/` packages. This file is the single home for what the bytes on disk mean; interpreting them (which stage reads which marker, when to gate) belongs to the skills that drive flows, not here.

## Package

`.agents/work/<slug>/`, created on first use:

| File | Holds |
|---|---|
| `context.md` | inputs gathered (sources, facts, prior art) - not decisions |
| `scenarios.md` | test scenarios, when a test plan is made |
| `requirements.md` | R entries |
| `decisions.md` | sections: Decisions (D), Open questions (Q), Deferred, Friction (X), plus the chart-pass sections `## Destination` and `## Not yet specified` (written when a design effort opens; the destination seeds a dev cycle's launch-gate outcome); a full dev cycle appends `## Outcome`, `## Deviation log` (implement stage's filed copy of the implementer's returned log), `## Review findings` (code-review stage's scored findings, consumed and dispositioned by verify-fix), `## Review nits`, and `## Contract mode` (contract-mode notes when a cycle runs in a repo with a requirements contract) |
| `<topic>.md` | optional deep-dive notes; forks found there go into `decisions.md` as Q |
| `spec.md` | the spec produced by a cycle's spec stage; carries `Reviewed:` footer markers |
| `plan.md` | the checkbox-tracked implementation plan; carries `Reviewed:` footer markers and the `Implemented` footer line |
| `mailbox/` | inter-session mailbox for linked sessions; layout and contract owned by the mailbox skill |
| `attack-claims/` | adversarial claim-verification runs: `<topic>/claims.md` ledger, `logs/`, `report.md`; layout and contract owned by the attack-claims skill |

One ID scheme per package; IDs are never reused.

## State line

First line of package `decisions.md`: `state: <value>` (lowercase, kebab).
Absent = legacy package; consumers fall back to file-presence detection.
A present-but-unknown or malformed state line is a defect, not a legacy
package: consumers report it and stop; the lint names the allowed values.
Canonical enum (defined in `scripts/package_states.py`, mirrored here;
the lint validates against the same list and a CI test asserts equality):

state: grill | test-plan | spec | plan | implement | code-review | verify-fix | complete | research | root-cause | pattern-analysis | hypothesis | implementation | resolved

Dev-pipeline stages: grill, test-plan, spec, plan, implement,
code-review, verify-fix, complete. Debug-cycle phases
(systematic-debugging): root-cause, pattern-analysis, hypothesis,
implementation, plus terminal `resolved`. The launch gate is a checkpoint,
not a state: resumes into autonomous stages (including `state: verify-fix`)
pass it; `complete` and interview restarts do not - the driving skill
defines which resumes are autonomous.

Research (in-progress): `research` marks an in-progress research spike,
written by the spike-driving skill; it is not a dev-pipeline or debug-cycle
phase. Terminal transition: `grill` when the spike surfaced open Q entries,
else the package's prior state (`complete` for a package the spike created).
`fix-attempts:` is forbidden in it.

Precedence: when present, the state line is authoritative - file presence
and markers refine within the named stage but never override it. One
exception: open Q entries in `decisions.md` pull the state back to `grill`
(the driving skill rewrites the line) - never while the state is `research`:
the spike-driving skill owns the line until its terminal transition, and a
spike attached to a grill package holds open Qs throughout.

Debug packages carry a second line directly after `state:`:
`fix-attempts: <int>` - required in the five debug states, forbidden
otherwise; incremented on each failed fix; re-read from disk after
compaction, never trusted from memory.

On stage completion the dev cycle's driving skill runs the guarded writer in
this directory: `uv run --script <this skill's directory>/advance.py <package-dir> --expect-state <cur> --set-state <next>`
- it refuses on any mismatch (printing actual vs expected, no write) and
validates the seven dev-pipeline chain transitions; debug-cycle and research
transitions stay the driving skills' prose. `scripts/check-packages.py` (CI)
validates syntax.

## Entry formats

```markdown
- R3 (2026-10-05). The admin tenant is never rate limited. Source: user. Scope: new.
- D4 (2026-10-05). **Token bucket.** Rejected: fixed window (bursts at edges). Resolves Q1.
  Consequences: ... Serves R3.
- D8 (2026-10-05). **Bucket TTL = time to full.** Rejected: no TTL (idle keys pile up).
  Agent-picked.
- ~~D2 (2026-10-02). Redis counters.~~ Superseded by D5 (ops won't provide Redis).
- Q2. How does the LB learn the tenant? (a) header (b) key only. Recommended: (a) - ...
- X1 (2026-10-06). Plan said sync `check()`; middleware is async. -> D7.
- Deferred: hot reload of limits. Revisit when: a tenant needs a limit change without restart.
```

- **R** = an observable behaviour or a constraint future choices must respect, worded so it can be
  verified, and no broader than the source said. Scope is `new` or `amends <contract
  handle>` - a repo requirements contract's ID, or that contract's stable handle
  (heading, name) when it has no IDs.
- **D** = a choice between alternatives, naming what was rejected. A D the user didn't make
  ends with `Agent-picked`, so the user can see what to review.
- **X** = reality disagreed with the design; always points to the D or Q it produced.
- A resolved Q is removed and cited by the D that resolved it.

## Dependency edges

Plan tasks and Open-questions entries may declare what blocks them. Same-file
edges only: plan tasks block plan tasks, Q entries block Q entries.

- Plan task: a `**Blocked by:**` line under the task heading - `Task 2, Task 4`
  references or `None`. Required on every task once any task in the plan has
  it (a plan with none anywhere is legacy and passes untouched). A task is
  closed when every checkbox under its heading is checked.
- Q entry: an optional `Blocked by: Q2, Q3` in the entry, and an optional
  type tag after the ID - `- Q3 [research] ...` - one of grill (the default,
  untagged), research, prototype, task. A Q is closed when struck through or
  when some D carries `Resolves Q<n>`; resolution still removes the entry,
  the citation is the closure record.

`graph.py` in this directory checks a package mechanically
(`uv run --script <this skill's directory>/graph.py check <package-dir>`):

- `check` - findings, one per line, exit 1 on findings: a reference that
  resolves to no task and to no open/struck/`Resolves`-cited Q; a cycle; a
  closed plan task with an open blocker; an opted-in task missing the field;
  a second `Blocked by` line on one task; a `Blocked by` line outside any
  task heading; an opted-in task with no checkboxes (it could never close);
  a duplicate task or Q ID; a cross-file reference; an unparseable
  reference; an unknown type tag; a duplicate live D id or a live D colliding
  with a struck one; step labels that duplicate or skip numbers within a task
  (numbering starts at 1 and lettered variants count as their base). Q
  entries parse only under an `## Open questions` heading, and only D entries
  carry `Resolves` closure.
- `frontier` - the open items whose blockers are all closed, as a JSON array
  in file order (plan tasks in plan order, then Qs in decisions order), each
  `{id, kind: task|q, type, title, blocked_by}`; plan-task items carry
  `type: null`, an untagged Q reads as grill. Exit 1 and no array when check
  reports findings. Pick the next item with jq: `frontier <dir> | jq '.[0]'`.
- `tick` - flips a task's unchecked boxes to `[x]` in place (the tool's one
  write): errors with no write on an unknown task number, an ambiguous plan
  (duplicate task numbers), a task with no checkboxes, or one already fully
  checked; fenced lines are never touched.
- `detect` - JSON facts, no routing decision: the state line (or its
  absence), `## Outcome` and `## Review findings` presence, live D count,
  open Q count, and per-artifact existence/marker facts including plan box
  counts; errors on an absent decisions.md or a malformed state line.

This repo's package lint runs `check` across every package; other repos run
the script directly.

## Markers

Bytes that cycle-driving skills read back; the writes are `advance.py`/`sections.py` in this directory (the byte shapes stay this contract's). Their *interpretation* (which stage consumes which marker) stays with the driving skill:

- `Reviewed: pass|fail <n>` - appended to an artifact footer after each reviewer round by `advance.py --review <verdict> --artifact spec|plan` (round continuity enforced, gaps and duplicates refused, never renumbered); `<n>` counts rounds over the artifact's lifetime.
- `Implemented` - appended to a plan footer by `advance.py --implemented` when implementation completes; an existing marker is refused, never duplicated.
- `## Outcome` - section in `decisions.md` recording the confirmed outcome at the launch gate (`sections.py insert outcome` creates the heading; the driving stage writes the body under it).
- `## Deviation log` - section in `decisions.md` where the implement stage files the implementer's returned deviation log (`sections.py insert deviation-log` creates the heading; the stage pastes the log under it) before the state moves to code-review.
- `## Review nits` - section in `decisions.md` where LOW review findings live; appended per round by hand (the insert-once `sections.py` command cannot serve an append-per-round section).
- `## Review findings` - section in `decisions.md` where the code-review stage files its scored findings (`sections.py insert review-findings` creates the heading; the stage writes the numbered findings under it) before the state moves to verify-fix; the verify-fix stage triages from this copy, filing each finding's disposition with `sections.py disposition <n> "<text>"`.

## Legacy conversion

Package slug: `<date>-<topic>` (e.g. `2026-10-14-agent-state-machine-spike`);
debug investigations append `-debug`.

A `.agents/plans/` directory is the pre-rename location of `.agents/work/`:
when only it exists, treat it as the canonical package store and rename the
directory on next touch (contents unchanged); when
both exist, reconcile before editing. A flat `<date>-<topic>-decisions.md` /
`-spec.md` / `-plan.md` triple is a pre-package cycle. Read its shared basename as the package dir, and at the next gate convert, not just move: put the three files into `.agents/work/<basename>/` as `decisions.md` / `spec.md` / `plan.md`, renumber the legacy `## Design decisions` lines as D entries, and extract the `## Test scenarios` section into `scenarios.md`.
