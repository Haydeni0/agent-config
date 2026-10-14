---
name: research-spike
layer: orchestrator
description: Run a research spike - decompose an open question into independent investigation streams, fan them out (capped), and synthesize evidence-backed findings into a work-package. Invoke only via /research-spike or an explicit request to run a research spike.
deps: [librarian, living-doc, work-package]
exits: ['context.md', 'decisions.md Q entries (when the research surfaces open forks)']
---

# research-spike

## Overview

Run a research spike: take one open question, split it into independent
investigation streams, run them as fresh full-tool subagents, and
synthesize their findings into a work-package. Streams write evidence
files; the orchestrating session synthesizes and files decision-ready Q
entries. Disk is the record: a compacted or dead session resumes the
spike from the package, never from memory.

Load work-package before creating or writing any package file. Load
librarian and living-doc only as the briefs below direct - their bodies
are the contract for the streams, restated nowhere here.

## On invocation: package selection

Pick the package first, from the target project's `.agents/work/`:

- A named or active package whose state is `grill`, `complete`, or absent
  (legacy) attaches: findings append to its existing `context.md`, stream
  files land alongside.
- A package at `state: research` is a spike in progress: resume it (below).
- A `grill`, `complete`, or absent-state package whose latest spike
  section (below) still lists a `pending` stream is an interrupted
  fan-out - the session died between the two fan-out writes: write
  `state: research` and resume it.
- Any other state (a build in flight, a debug cycle) is never attached to:
  say so and create `<date>-<topic>` instead - attaching would strand a
  live cycle mid-stage.
- No match: create `<date>-<topic>` (slug per work-package). The spike
  creates the package's `decisions.md`; until synthesis it may hold only
  the state line.

Record the attached package's prior state - the spike section (below)
writes it durably; the terminal transition reads it from there, never
from memory.

## Decomposition

Split the question into independent streams. Each stream gets:

- a one-line sub-question
- a kind: `read` (search/read sources), `probe` (run something to
  observe behavior), or `sweep` (broad scan across many sources)
- in-scope and out-of-scope, one line each
- its own output filename (below), not already present in the package -
  an earlier spike's stream files stay untouched

Streams must be independent: no stream needs another's output to finish.

## Decomposition gate

Human present: print the question, the streams (sub-question, kind,
scope), and which run concurrently; wait for `go` or edits. Spawn
nothing before `go` - the user sees the split before paying for it.
Dispatched by orchestrator (or any caller's brief): the brief stands in
for `go` - proceed with no pause.

## Fan-out: spike section and state line

At fan-out time, after the gate, before the first spawn, two writes in
this order - same for attached and created packages:

1. Append a spike section to `context.md`: heading
   `## Spike <n>: <question>`, `<n>` one more than the highest spike
   section already there (1 for the first). Its first line is
   `Prior state: <value>` - the attached package's state value, `legacy`
   when its `decisions.md` had no state line, or `created` for a package
   the spike created. Then a **Sources** list naming every stream: name,
   file, `status: pending`.
2. Write `state: research` as the first line of `decisions.md`.

Once `state: research` overwrites that first line, `Prior state:` is
the only durable record of what to restore. A crash between the two
writes leaves `pending` streams under the prior state - package
selection resumes that as an interrupted fan-out.

Update each stream's status in place as it finishes: `done`, or
`failed: <reason>`. The latest spike section's Sources is the sole
durable record of the decomposition - it is what a compacted or dead
session resumes from. Earlier spike sections are finished records; never
edit them.

## Concurrency

Up to 6 streams in flight; total stream count is uncapped. Launch
remaining streams as earlier ones finish. Where the harness offers no
subagent dispatch, run the streams sequentially inline in this session -
same briefs, same files, same Sources updates.

## Resume

A package at `state: research`: the latest spike section's Sources is
the authoritative decomposition - do not re-decompose. A human-present
resume re-prints Sources and waits for `go` or edits (same gate); a
dispatched resume proceeds on its brief. Then key each stream on its
Sources status:

- `failed: <reason>` is settled - never re-run it.
- `pending` with no file re-runs under the 6-cap, same brief.
- `pending` whose file exists is done - the file overrides a stale
  `pending`.

Every stream settled but no Synthesis yet: go straight to Synthesis.

## Stream brief

Each stream is one fresh general-purpose subagent with full tools,
bounded by blast radius: read, search, clone, build, and run probes only
in throwaway locations (scratchpad, `/tmp` clones, isolated worktree
when probing the target repo, worktree removed after); never mutate the
user's working tree, remotes, shared services, or global environment
(global package installs, PATH or shell config, system state); anything
built is labelled throwaway; the report carries evidence (commands run,
outputs, permalinks).

A probe needing a tool only a global install can provide falls back to
reading source and names the requirement in its report - the ban is on
the mutation, not on having the answer.

The brief carries only spike-specific content - question, scope,
throwaway rule, output path, return shape, skill-loading directives.
Streams inherit evidence discipline by loading skills, never from
embedded rule copies. Template:

```
Stream: <name>. Investigate: <one-line sub-question>.
Done when: <observable done-condition>.
In scope: <line>. Out of scope: <line>.
Blast radius: throwaway locations only (scratchpad, /tmp clones,
isolated worktree for repo probes, removed after); never mutate the
user's working tree, remotes, shared services, or global environment
(global package installs, PATH or shell config, system state); label
anything built throwaway; report carries evidence (commands run,
outputs, permalinks).
Load the living-doc skill: your output file is a living doc. Create the
skeleton at <package>/<stream>.md (filename kebab-case, never a
work-package contract filename); this brief's question + done-condition
stand in for START's interview - do not ask it; work under its Working
rules; FINALISE the doc before replying.
[When the stream cites library or repo source:] Load the librarian
skill and follow its citation rules.
Reply with a short summary only - the file is the real deliverable.
```

The orchestrating session is the sole writer of `context.md` and
`decisions.md`; streams write only their own stream file.

## Stream failure

Crash or missing file: one retry with the same brief. Second failure:
mark the stream `failed: <reason>` in Sources, name the gap in the
Synthesis, and make any Q entry resting on it say so. A gap that blocks
the question puts `INCOMPLETE: <what remains>` directly under the spike
section's `Prior state:` line.
Never abort the spike on one stream; never retry past one.

## Synthesis

When Sources shows no `pending`:

1. Add a **Synthesis** subsection to the spike section answering the spike
   question from the stream files, with evidence citations into them.
2. File Q entries in `decisions.md` for open forks the research
   surfaced - decision-ready: options + recommendation, work-package
   entry format.
3. Contradictions are loud: both sides stated with evidence. A factual
   dispute a cheap targeted check can settle gets one follow-up stream -
   same brief and file rules, under the 6-cap, added to Sources with the
   same in-place status updates. Otherwise it becomes a Q whose options
   are the competing readings. Never silently adjudicate.
4. A load-bearing claim no second stream corroborates is weak evidence,
   not settled fact. A cheap targeted check exists (independent source,
   or the cited document/repo source itself for read/sweep citations):
   one corroboration follow-up stream, same brief and file rules as a
   contradiction follow-up, checking the independent source - or, for
   a claim resting on cited documents or repo source, confirming each
   load-bearing citation says what the stream file claims. No cheap
   check, or the stream settles and the claim still stands alone: the
   Synthesis states the claim as single-sourced in the same breath as
   any answer resting on it - never propping a headline the caveat
   contradicts.

## Terminal state

Write the terminal state as the first line of `decisions.md`:

- `state: grill` if the spike filed open Q entries - the user decides.
- Else `state: complete` when the spike section's `Prior state:` line
  reads `created`.
- Else the attached package's prior state, restored from the
  `Prior state:` line - never from memory.
- A `Prior state: legacy` package stays legacy: remove the
  fan-out-written `state: research` line at synthesis - leaving it
  would strand the package permanently in-progress.
