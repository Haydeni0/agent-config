---
name: work-package
layer: worker
description: Use when reading, writing, or resuming work in a `.agents/work/<slug>/` package, or when another skill cites this contract. Holds the on-disk contract - package layout, file roles, entry formats, ID rules, marker formats, and the legacy conversion recipe. Load it before reading or writing package files.
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
| `decisions.md` | sections: Decisions (D), Open questions (Q), Deferred, Friction (X); a full dev cycle appends `## Outcome`, `## Review findings` (code-review stage's scored findings, consumed and dispositioned by verify-fix), and `## Review nits` |
| `<topic>.md` | optional deep-dive notes; forks found there go into `decisions.md` as Q |
| `spec.md` | the spec produced by a cycle's spec stage; carries `Reviewed:` footer markers |
| `plan.md` | the checkbox-tracked implementation plan; carries `Reviewed:` footer markers and the `Implemented` footer line |

One ID scheme per package; IDs are never reused.

## State line

First line of package `decisions.md`: `state: <value>` (lowercase, kebab).
Absent = legacy package; consumers fall back to file-presence detection.
A present-but-unknown or malformed state line is a defect, not a legacy
package: consumers report it and stop; the lint names the allowed values.
Canonical enum (defined in `scripts/package_states.py`, mirrored here;
the lint validates against the same list and a CI test asserts equality):

state: grill | test-plan | spec | plan | implement | code-review | verify-fix | complete | root-cause | pattern-analysis | hypothesis | implementation | resolved

Dev-pipeline stages: grill, test-plan, spec, plan, implement,
code-review, verify-fix, complete. Debug-cycle phases
(systematic-debugging): root-cause, pattern-analysis, hypothesis,
implementation, plus terminal `resolved`. The launch gate is a checkpoint,
not a state: resumes into autonomous stages (including `state: verify-fix`)
pass it; `complete` and interview restarts do not - the driving skill
defines which resumes are autonomous.

Precedence: when present, the state line is authoritative - file presence
and markers refine within the named stage but never override it. One
exception: open Q entries in `decisions.md` pull the state back to `grill`
(the driving skill rewrites the line).

Debug packages carry a second line directly after `state:`:
`fix-attempts: <int>` - required in the five debug states, forbidden
otherwise; incremented on each failed fix; re-read from disk after
compaction, never trusted from memory.

The cycle-driving skill writes the state line on stage completion
(systematic-debugging in debug cycles; the dev pipeline's orchestrator in
dev cycles). `scripts/check-packages.py` (CI) validates syntax;
transitions are the driving skills' prose.

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
  verified, and no broader than the source said. Scope is `new` or `amends <global REQ-ID>`.
- **D** = a choice between alternatives, naming what was rejected. A D the user didn't make
  ends with `Agent-picked`, so the user can see what to review.
- **X** = reality disagreed with the design; always points to the D or Q it produced.
- A resolved Q is removed and cited by the D that resolved it.

## Markers

Bytes that cycle-driving skills write on artifacts and read back; their *interpretation* (which stage consumes which marker) stays with the driving skill:

- `Reviewed: pass|fail <n>` - appended to an artifact footer after each reviewer round; `<n>` counts rounds over the artifact's lifetime.
- `Implemented` - appended to a plan footer when implementation completes.
- `## Outcome` - section in `decisions.md` recording the confirmed outcome at the launch gate.
- `## Review nits` - section in `decisions.md` where LOW review findings live.
- `## Review findings` - section in `decisions.md` where the code-review stage files its scored findings before writing `state: verify-fix`; the verify-fix stage triages from this copy and appends each finding's disposition.

## Legacy conversion

A `.agents/plans/` directory is the pre-rename location of `.agents/work/`:
when only it exists, treat it as the canonical package store and rename the
directory on next touch (contents unchanged); when
both exist, reconcile before editing. A flat `<date>-<topic>-decisions.md` /
`-spec.md` / `-plan.md` triple is a pre-package cycle. Read its shared basename as the package dir, and at the next gate convert, not just move: put the three files into `.agents/work/<basename>/` as `decisions.md` / `spec.md` / `plan.md`, renumber the legacy `## Design decisions` lines as D entries, and extract the `## Test scenarios` section into `scenarios.md`.
