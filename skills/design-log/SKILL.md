---
name: design-log
layer: orchestrator
description: Use when designing or planning a feature or new body of work across turns or sessions - a design grill, writing a spec or plan from a design, implementation that diverges from the agreed design, or "wrap up / finalise the design docs".
deps: [grill-me, test-plan, write-spec, writing-plans, plan-package]
---

# Design log

## Overview

A design lives in one local package per piece of work. Every requirement, decision, open
question and implementation surprise is written there **when it happens**, so specs, plans and
code cite it instead of becoming a second, drifting source of truth. Repo-global docs are
updated only at an explicit promote step.

## Package

The package layout, file roles, entry formats, ID rules, marker formats, and the legacy conversion recipe are the plan-package skill's contract - load it before reading or writing package files. This skill adds only the discipline of *when* entries get written, below.

## When to write

| Observable trigger | Write, before replying or continuing |
|---|---|
| User answers a fork | D |
| User says must / never / always / has to about behaviour, or states a constraint | R (not a D) |
| A new fork appears that the user should decide | Q |
| Writing a spec/plan, you pick something no existing D covers | D, or Q if it's the user's call; the spec cites the ID |
| Implementation can't follow the spec/plan, or a design assumption proves false | X plus D/Q, then tell the user |
| User reverses a decision | strike the old D, add the new D, link both |

Specs and plans reference IDs - "Admin bypass (D5, R3)" - and list open questions as IDs
pointing into `decisions.md`. They never hold requirements, decisions or questions that the
package lacks.

## Orchestrating

When the user drives design work through this skill, compose the workers and file their
output into the package:

- Design not settled -> run grill-me. User answers become D entries here (R instead when
  they say must / never / always); new forks become Q.
- Test scenarios wanted -> run test-plan; file its output as `scenarios.md`.
- Spec wanted -> run write-spec; destination is the package's `spec.md`. Any pick the
  spec makes that no D covers is logged here first, and the spec's open questions become
  Q entries here - the spec lists their IDs, never the questions themselves.
- Plan wanted -> run writing-plans; destination is the package's `plan.md`.

"The design is settled - write the spec / plan" routes to the worker, not to Promote.
Promote fires only when the user says the design work is done / finalised / wrapped up.

## Promote

Only when the user says the design is done / finalised / wrap it up.

1. Read the `AGENTS.md` Documents map. If the package has user-visible behaviour only inside
   Ds (no R for it), draft the Rs with `Source: D<n> (draft)`, show them, and promote only after
   the user confirms the wording.
2. A requirements document is listed: add each R that describes user-visible behaviour, in that
   document's format and ID scheme (e.g. `REQ-AREA-NN`, Statement, Verification - mark a planned
   test as planned). Implementation choices stay D; they never become REQs.
3. A decisions/design log is listed: append the settled Ds in its format.
4. Nothing listed: skip steps 2-3; the package is the record.
5. Add a header to `decisions.md`: `Promoted <date>: R1 -> REQ-RATE-01, ...`.

## Common mistakes

| Mistake | Fix |
|---|---|
| "This follows from D2, not a new decision" | If it rules out an alternative, it's a D. Log it. |
| Open questions listed only in the spec | Move them to `decisions.md`; spec cites IDs. |
| Deviation noted in plan checkboxes or chat only | X entry; plan note may link it. |
| "Must never X" logged as a decision | It's an R. |
| R widened beyond what the user said ("no Redis" -> "no external store") | Word it as stated; widen only if the user agrees. |
| Requirements written at wrap-up from decisions | Write R when stated; wrap-up only promotes. |
