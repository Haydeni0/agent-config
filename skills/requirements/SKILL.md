---
name: requirements
description: Use when writing, updating, citing, or auditing a binding requirements contract - a repo's canonical requirements/spec file with stable IDs and verification pointers. Covers adding or amending entries, writing manual verification procedures, deciding what belongs in the contract (the promotion filter), and running the contract lint. Not for per-cycle package R entries (work-package owns those).
---

# requirements

Reference contract for binding requirements contracts - the single home for
what the rules ARE. Interpretation belongs to the consumers: repo-agent-setup
provisions contracts in repos; dev-cycle detects and enforces them at its
stages; plain chat edits cite this skill.

## Entry format

Each entry has:

1. a stable ID in the repo's own scheme (e.g. `REQ-AREA-01`). IDs are stable
   and never reused; a new area gets a new section.
2. one observable Statement of user-visible behavior - one behavior per
   entry. Compound legacy entries split on next touch, minting new IDs. An
   undecided point is written `undecided: <what>` in the Statement - never
   guessed, never omitted.
3. a Verification pointer - an automated test preferred; when that is
   impossible, the exact manual procedure, written given/when/then so it is
   mechanical to follow. `planned` marks an accepted behavior whose proof
   does not exist yet - the obligation stays explicit on the row.

## Promotion filter

Only observable, durable, user-visible behavior becomes an entry.
Implementation detail, internal refactors, and non-observable design choices
never promote - they live in the repo's design or decision records.

User-visible means: anything a repo user (maintainer, agent, downstream
consumer) could run or perform and observe - CLI output and exit codes,
file/link/hook effects, test outcomes, documented workflow results.
Never user-visible: internals with no observable effect, refactors, code
organization, dependency swaps without behavior change, implementation
strategy.

## Citation and maintenance

Cite entries as ID plus one-line meaning; quote the statement verbatim when
interpretation matters. Update the contract with or before any behavior
change. Never mark work complete without running the entry's cited
verification.

## Lint

`lint.py` in this directory checks a contract table: duplicate IDs, and
citation resolution (every backtick-quoted file path a Verification cell
names resolves from the repo; `manual (...)` procedure spans and `planned`
pointers are skipped). Run from the target repo's root:

```bash
python <this skill's directory>/lint.py docs/requirements.md
```

Exit 0 = clean; findings print one per row ID; exit 2 means no contract rows
parsed (wrong file or unknown ID scheme).
