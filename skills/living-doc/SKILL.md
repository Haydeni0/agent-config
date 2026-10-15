---
name: living-doc
description: Use when starting an investigative, debugging, or setup/config task you'll later need to reproduce or hand to future-you, or when asked to "keep a living doc" or "make a reference doc", or to resume or finalise one. Also triggered by /living-doc.
argument-hint: "[resume <name> | finalise [<name>]]"
deps: [claim-verification]
---

# living-doc

## Overview

A living doc is an evidence-grounded markdown reference, built *during* an investigation or setup task, that lets future-you redo the task without re-investigating. Core rule: **nothing enters the doc that isn't grounded in evidence you observed this session.** No guesses, no recalled-from-training "facts", no plausible-sounding mechanisms. A polished doc full of unchecked claims is the failure this skill exists to prevent.

## When to use

- Investigative, debugging, or setup/config sessions you'll need to reproduce or reference later
- Tasks with non-obvious steps where "how did we do this?" is a future risk

**Not for:** quick one-off tasks with no reproduction value, or creative/writing work with no findings to ground.

## Modes - dispatch on `$ARGUMENTS`

| `$ARGUMENTS` | Mode |
|---|---|
| empty, `start`, or `start <name>` | **START** |
| `resume <name>` | **RESUME** |
| `finalise` or `finalise <name>` | **FINALISE** |

## START

1. Ask exactly these two questions, adding your interpretation of the user's likely answer only when the user's request gives enough context to infer it; otherwise ask without an interpretation and wait for answers (always, even if a name was given):
   - **Goal** - what are you trying to achieve?
   - **Success criteria** - how will you know it's done?
   When adding interpretations, use this format:
   ```markdown
   **Goal** - what are you trying to achieve?
   Interpretation: I think you want to <agent's concrete read of the goal>. Is that right?

   **Success criteria** - how will you know it's done?
   Interpretation: I think this is done when <agent's concrete read of completion>. Is that right?
   ```
2. If `start <name>` supplied a name, use it. Otherwise propose a concise, sensible name from the task and get the user's OK before creating the file.
3. Create `<name>.md` at the workspace root with this skeleton:
   ```markdown
   # <name>
   > Created via `/living-doc`. Resume with `/living-doc resume <name>`.
   ## Goal
   ## Success criteria
   ## Findings   <!-- verified facts -->
   ## Steps      <!-- actions confirmed to work; order at finalise -->
   ## Gotchas    <!-- dead ends, surprises, corrections -->
   ```
4. Do the task, maintaining the doc per **Working rules** below.

## RESUME `<name>`

Read the existing `<name>.md`. Confirm in one question whether **Goal** and **Success criteria** still hold (update them if not). Then continue the task under **Working rules**.

## FINALISE `[<name>]`

If `<name>` is omitted, finalise the doc created or resumed this session; if that's ambiguous, ask which. Review the doc against what actually happened this session, using evidence:

- **Order** the Steps into the real reproduction sequence (during the task they accrete out of order - fix that now).
- **Move** dead ends, backtracks, and surprises out of Steps into Gotchas.
- **Cut redundancy** - merge duplicate points. Be concise, but lose no information needed to reproduce the task or understand a gotcha. Strip the skeleton `<!-- -->` comments.
- **Re-check every claim is evidence-grounded.** Run claim-verification on the doc as a terminal message. Resolve every `[unverified]` marker: verify it, or delete it. Nothing unverified survives finalise.
- **Cross-check the doc against itself.** A Step must not assert what the Findings or Gotchas disprove (e.g. Steps says "`brew install` gives 0.35.0" while Findings show it now ships 0.42.0). Fix the loser; the doc must not contradict itself.
- **State the outcome honestly.** If success criteria is NOT met, the doc says so on its face - a first line under Goal or a top status line: "INCOMPLETE as of <date>: <what remains>." A finalised doc with unmet criteria that reads like a finished reference is the failure mode: it looks authoritative while describing a half-done investigation. Do not polish an unfinished investigation into something that looks complete.
- **Retire when stale, not silently.** On RESUME, check the doc's dated empirical claims against current reality (the recorded re-check commands make this cheap). When a claim is disproven, correct it. When the doc's *purpose* is served by something else (the thing it documented shipped, was renamed, or a newer doc supersedes it), retire it explicitly: mark it superseded with a pointer to the successor (or delete it if the user confirms), never leave it silently aging while looking authoritative.

## Working rules (START + RESUME)

- **Evidence only.** Write a fact only after observing it this session: command output, file contents you read, an authoritative doc/source you actually opened. A step counts only once you ran it end-to-end and saw it succeed (output, return value, or other observable artifact) - not "I'm fairly sure it works".
- **Label the unverified.** Something plausible but not yet confirmed → prefix the line with `[unverified]`. Verify or delete before finalise; never let it harden into fact.
- **Date empirical claims.** A finding that states a measured value, an observed behavior, or an environment fact gets the date it was verified plus, where practical, the command that re-verifies it: "`MAX_RETRIES=3` (repo `api/config.py`, checked 2026-09-01; re-check: `grep MAX_RETRIES api/config.py`)". A stale dated claim is discoverable - an undated one is invisible rot. Use the date the evidence was actually observed, not today's date when writing.
- **No invented mechanisms.** Don't claim "X causes Y", "X is the default", or "it's A not B" from a correlation, a name, a single observation, or memory. Confirm it in *this* environment, or mark `[unverified]`. **If two explanations fit your evidence equally** (e.g. a value that happens to match in two places), you have confirmed neither - record what you *observed*, not the mechanism you inferred.
- **Update continuously** - after each verified finding, and whenever the user asks.
- **Contradictions are loud.** When new evidence disproves something already in the doc, tell the user ("Doc said X; just confirmed Y - correcting"), then fix it immediately. Never leave a known-wrong line sitting.

## Red flags - you're guessing, not grounding

- Writing "should be", "typically", "by default" without having run or read it
- Documenting a file/function/config without confirming it's the one actually invoked - trace from the real entrypoint when lookalike copies or variants exist (`.sh` vs `.js`, an inactive config, a shadowed path)
- Filling a section because it "ought to have content" rather than because you have evidence

All of these mean: verify it now, or mark `[unverified]`.

## Common mistakes

| Mistake | Fix |
|---|---|
| Skipping the Goal/Success interview | Always ask the two questions first - they focus what's worth recording |
| Documenting how you figured it out | Steps = how to *redo* it, not the investigation narrative; narrative belongs in Gotchas only if useful |
| Polished doc full of unchecked claims | Polish is not grounding. Every claim needs evidence |
| Asserting a mechanism that merely *fits* the evidence | If `name: tdd`, dir `tdd/`, and command `/tdd` all match, you can't claim which one drives the command - record the observation, not the cause, or mark `[unverified]` |
| One rigorously-verified fact vouching for its neighbours | Verifying the hard part doesn't ground the easy-looking claims next to it. Each stands on its own evidence |
| Treating `[unverified]` as a dumping ground | It tags a genuine partial finding you intend to confirm - keep those, labelled. Pure speculation you won't test doesn't go in at all |
| Skipping the finalise pass | The doc isn't "done" until finalised - ordered, deduped, all `[unverified]` resolved |
| Finalising an unmet-criteria doc that reads complete | Success criteria unmet = the doc says "INCOMPLETE as of <date>" on its face. A polished-looking reference describing a half-done investigation misleads the next reader |
| Empirical claims without dates | Every measured value / environment fact carries when it was verified + re-measure command where practical. Undated claims rot invisibly; dated ones are discoverably stale |
