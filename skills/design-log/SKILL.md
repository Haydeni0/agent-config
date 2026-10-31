---
name: design-log
layer: orchestrator
description: Use when designing or planning a feature or new body of work across turns or sessions - a design grill, writing a spec or plan from a design, implementation that diverges from the agreed design, or "wrap up / finalise the design docs".
deps: [grill-me, test-plan, write-spec, writing-plans, work-package, requirements, research-spike, prototype]
---

# Design log

## Overview

A design lives in one local package per piece of work. Every requirement, decision, open
question and implementation surprise is written there **when it happens**, so specs, plans and
code cite it instead of becoming a second, drifting source of truth. Repo-global docs are
updated only at an explicit promote step.

## Package

The package layout, file roles, entry formats, ID rules, marker formats, and the legacy conversion recipe are the work-package skill's contract - load it before reading or writing package files. This skill adds only the discipline of *when* entries get written, below.

## Opening a design: the chart pass

Before answering anything in a package design-log opens, chart it
breadth-first. Write the `## Destination` section in the decisions file - one
or two lines, what reaching the end of this work looks like; every later
session orients to it. File the sharp questions as typed Q entries with
their blocking edges. Fill a `## Not yet specified` section with the in-scope
fog: questions you can tell are coming but cannot state precisely yet. The
sharpness test: if the question can be stated precisely now, it is a Q entry
however unanswerable; if it cannot, it is fog. Do not pre-slice fog into
question-sized pieces - one patch may graduate into several questions, or
none. Out-of-scope work stays in Deferred entries; fog never holds it.

`## Destination` names where the effort heads; it is unrelated to write-spec's
save-location label of the same word.

Then hand the frontier order to grill-me and let it resolve the questions one
at a time. When a decision lands, re-read the fog section: graduate whatever
the answer has made sharp enough to state into new Q entries and delete it
from fog.

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

- Design not settled -> run grill-me, working the questions in frontier order
  (run the work-package graph tool's `frontier` on the package directory and
  take the first item - not a re-read-and-judge). Tag new forks when you file
  them: `[research]` when the answer is knowledge outside the working
  directory (route to research-spike), `[prototype]` when the question is how
  it should look or behave (route to the prototype skill), `[task]` when
  manual work must happen before any decision can be made (do it directly or
  hand the user a checklist); untagged means grilling. User answers become D
  entries here (R instead when they say must / never / always); new forks
  become Q.
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
   document's format - the requirements skill owns the entry rules (format, promotion filter,
   planned pointers); load it before writing entries. Implementation choices stay D; they never
   become REQs.
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
