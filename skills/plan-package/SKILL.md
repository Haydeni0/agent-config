---
name: plan-package
layer: worker
description: Use when reading, writing, or resuming work in a `.agents/plans/<slug>/` package, or when another skill cites this contract. Holds the on-disk contract - package layout, file roles, entry formats, ID rules, marker formats, and the legacy conversion recipe. Load it before reading or writing package files.
---

# plan-package

Reference contract for `.agents/plans/<slug>/` packages. This file is the single home for what the bytes on disk mean; interpreting them (which stage reads which marker, when to gate) belongs to the skills that drive flows, not here.

## Package

`.agents/plans/<slug>/`, created on first use:

| File | Holds |
|---|---|
| `context.md` | inputs gathered (sources, facts, prior art) - not decisions |
| `scenarios.md` | test scenarios, when a test plan is made |
| `requirements.md` | R entries |
| `decisions.md` | sections: Decisions (D), Open questions (Q), Deferred, Friction (X); a full dev cycle appends `## Outcome` and `## Review nits` |
| `<topic>.md` | optional deep-dive notes; forks found there go into `decisions.md` as Q |

One ID scheme per package; IDs are never reused.

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

## Legacy conversion

A flat `<date>-<topic>-decisions.md` / `-spec.md` / `-plan.md` triple is a pre-package cycle. Read its shared basename as the package dir, and at the next gate convert, not just move: put the three files into `.agents/plans/<basename>/` as `decisions.md` / `spec.md` / `plan.md`, renumber the legacy `## Design decisions` lines as D entries, and extract the `## Test scenarios` section into `scenarios.md`.
