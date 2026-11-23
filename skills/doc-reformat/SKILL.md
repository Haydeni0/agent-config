---
name: doc-reformat
description: Use when the user wants to reformat a messy or wall-of-text document for readability without losing any information, or invokes /doc-reformat (also /reformat-doc). Produces a scannable sibling copy (headers, lists, tables, bolded key terms) with a zero-loss guarantee enforced by a fresh-context audit against a literal-facts inventory.
---

# Reformat Doc (Zero-Loss)

Reformat an unstructured document for readability while preserving every literal fact.

## Inputs

`$@` is the document to reformat: a file path (read it), pasted text (use it directly), or nothing (ask the user for the path or text).

## On Invocation

Dispatch ONE orchestrator agent. Do not run the workflow inline. Pass the source doc path or text.

```
Agent(
    description="Reformat doc with zero-loss audit",
    prompt=<orchestrator prompt below, with SOURCE substituted>
)
```

## Orchestrator Prompt (verbatim, with SOURCE filled in)

You are an orchestrator. Reformat the source document for readability with a zero-loss guarantee. Source:

<SOURCE>
{{source path or text}}
</SOURCE>

Never modify the source file. Write the output to a sibling file: `[stem]-formatted.[ext]` (same dir, same extension). If SOURCE is pasted text with no path, write to `./reformatted-output.md`.

### Step 1 - Dispatch the Guardian (literal-facts inventory)

Dispatch a sub-agent. Its ONLY job: extract every literal fact from the source into a manifest. Literals are:
- numbers and metrics (latencies, counts, percentages, thresholds, sizes)
- URLs, hostnames, file paths, S3 URIs, ticket IDs, key IDs, service IDs
- code blocks (verbatim, including every line)
- dates and durations
- version numbers (go 1.22, postgres 16.1)
- proper nouns (people, products, repos, channels)
- config values and flag literals (sslmode=require, sslmode=disable, enabled: true, port numbers)

CRITICAL: comparison clauses like "the old X was Y" carry a literal (Y). Extract BOTH old and new values in any before/after pair. The old value is a fact, not disposable context. Missing these is the #1 failure mode.

Fuzzy time and soft deadlines ARE literals when they state a constraint or due date, even if imprecise. Extract "end of next week", "end of March", "before the next sync", "by end of Q1" verbatim - they are commitments, not filler. Missing these is the #2 failure mode (a Formatter reads a soft deadline as disposable prose).

If the same value appears twice in different contexts, list it twice (one manifest entry per occurrence), so the Loss Auditor checks each spot.

Capture surrounding quotes verbatim: if the source wraps a phrase in quotes (`"sawed-off cube"`, `'Issues'`), the manifest entry includes those quotes. The manifest IS the source of truth the Loss Auditor checks against - if it omits quotes the source had, the Formatter faithfully re-adding them reads as a mutation and costs a fix round.

Return the manifest as a numbered list. Each entry is one literal, with its value verbatim. Do not interpret, summarize, or decide what matters - extract exhaustively.

Then run the STALE-PATH ADVISORY (advisory only, never gating): among the extracted path-like literals (file paths, script names, directory refs - not URLs, not tokens), check which do NOT exist on the filesystem from the current working directory (`test -e` / `ls`). Report the misses in a one-line advisory note below the manifest, e.g. `Note: the source references paths that do not exist here: deploy.sh, /etc/app/config.yaml - stale or local-only; left untouched.` Never fix, never flag as an error, never let it affect the verbatim contract or the Loss Auditor gate. The doc may describe another machine's layout - this is a notice, not a correction.

### Step 2 - Dispatch the Formatter

Dispatch a sub-agent. Give it the source AND the Guardian's manifest. It produces the reformatted doc: clean headers, bullet lists, tables for before/after comparisons, bolded key terms. It MAY reword prose, reorder, merge redundant sections, and drop conversational filler.

**Verbatim contract (this is what prevents fix-loop rounds):** every manifest item appears in the output EXACTLY as in the manifest - same digits, same case, same characters, same surrounding punctuation. The only allowed changes are AROUND an item: bolding it, placing it in a table cell, reordering the containing sentence. Never change anything INSIDE an item:
- Don't spell out digits: `4` stays `4`, never `four`.
- Don't change case when bolding: `asteroids 1-3` bolded stays `asteroids 1-3`, never `Asteroids 1-3`.
- Don't swap character forms: ASCII hyphen stays ASCII, never Unicode minus; no non-breaking hyphens.
- Don't alter punctuation/spacing inside an item: `45° & 225°` keeps its spaces, `270` without a degree symbol stays without (preserve source typos verbatim).
- If a manifest item sits inside a sentence, keep the literal-containing phrase intact - don't split it across table cells. Put the whole sentence in one cell, or keep it as prose.

Before finishing, the Formatter self-checks each manifest item against the output and against this contract.

### Step 3 - Dispatch Loss Auditor and Quality Critic in parallel

Dispatch BOTH fresh-context sub-agents at once on the Formatter's output - they consume the same input, so run them concurrently, not sequentially.

- **Loss Auditor (hard gate):** give it the manifest and the formatted output ONLY (not the source). For each manifest item: present and unmutated per the verbatim contract? Any missing/mutated item is a FAILURE with item number and expected value. Returns PASS or a FAIL list.
- **Quality Critic (advisory):** grades scannability - text blocks over 4 lines, unbolded key terms, inconsistent list structure, broken markdown. Returns suggestions. Does NOT gate the build.

### Step 4 - Reconcile

- If Loss Auditor FAILs: send the fail list back to the Formatter, which fixes only those items, then re-dispatch BOTH auditors on the new output. Loop until Loss Auditor PASSes. This converges because the manifest is finite and the verbatim contract prevents the mutations that caused earlier rounds.
- If Loss Auditor PASSes: apply only the Quality Critic suggestions that don't drop or mutate any manifest item (re-run the Loss Auditor once if anything moves). Then finalize.

### Step 5 - Finalize

The orchestrator writes the final doc to the output path and reports: output path, manifest item count, and the Loss Auditor's PASS.

## Why This Shape

- **Guardian separate from Formatter**: under readability pressure the Formatter drops "old" values in comparison clauses while reporting no loss, so the inventory is fixed first.
- **Verbatim contract on the Formatter**: without it the Formatter mutates literals while formatting (`4` -> `four`, case changes on bolding, sentences split across table cells), and each mutation costs a fix round.
- **Loss Auditor fresh-context**: an auditor that shares the Formatter's context inherits its blind spots. Fresh context is the only check that catches what the Formatter decided was disposable.
- **Auditors in parallel**: Loss Auditor and Quality Critic read the same output, so run them concurrently - sequential ordering wastes a round trip per pass.
- **Quality Critic advisory, not blocking**: scannability is subjective and can loop forever. Loss is finite and converges. Only the finite gate blocks.
- **Original untouched, sibling output**: never mutate the source. The user compares and keeps what they want.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Formatter also does the Guardian's extraction | Separate sub-agents - the Formatter will shrink the inventory under readability pressure |
| Guardian skips "old" values in before/after clauses | Extract BOTH sides of every comparison; the old value is a literal |
| Guardian treats fuzzy time / soft deadlines as disposable prose | Extract imprecise commitments ("end of next week", "before the next sync") verbatim - they are constraints, not filler |
| Guardian drops surrounding quotes the source had | Manifest entry includes the quotes (`"sawed-off cube"`); omitting them makes the Formatter's faithful re-add read as a mutation |
| Loss Auditor sees the source | Give it manifest + output only, so it can't inherit the Formatter's blind spots |
| Quality Critic blocks the build | It's advisory; only the Loss Auditor gates |
| Mutating the source file | Never. Write a sibling `[stem]-formatted.[ext]` |
| Inventory includes prose intent, not literals | Literals only - numbers, URLs, code, dates, versions, names, config values. Intent is subjective and breaks convergence. |
