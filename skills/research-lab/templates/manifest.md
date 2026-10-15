# Evidence manifest (per experiment)

The manifest is the claims ledger (D20): one `Check` = one claim. It is Python because `expr`
is code; the generated ledger view (all claims, statuses, cross-index, DAG) is JSON.
Check semantics (value / range / quantifier, sign inside capture, split attribution, unit
agreement) are the F24 rules in
`../pilot/packages/2026-10-14-pxnet-interp-hub/audit/verifier-spec.md`.

```python
CHECKS = [
    Check(
        id="e17-c3",
        quote="Deep-layer cross/bc falls to 0.08-0.14 under the weighted encoder",  # verbatim
        data="results/e17_weighted_gno.json",
        expr="[d['weighted'][l]['cross_bc'] for l in range(1, 9)]",
        kind="range",                  # value | range | quantifier | novelty
        unit="",
        rounding=2,                    # prose rounds to 2 dp: exact match after rounding
        # claim-ledger fields (D20, D24)
        status="admitted",             # admitted | blocked | contradicted; set at the Decision step
        falsification="cross/bc >= 0.3 at any layer 1-8",   # from the brief's prediction
        forbidden="not evidence that accuracy is preserved", # what this must NOT be read as
        depends_on=["e9-c1"],
        audit_note="",                 # why the status last changed
    ),
]
```

Rules:
- Run the shipped checker from the skill root:
  `uv run --script scripts/lab_checker.py <manifest.py> <experiment.md>` - it runs
  `run_checks`, the `coverage_scan` over the Entry, and the cross-index, and exits
  non-zero on any failure.
- Prose numbers that are rounded are checked by **exact rounding** (`rounding=`), not a
  relative tolerance: a 2% tolerance let a mutated value through in the pilot.
- **Cross-index, both directions** (checker-enforced): every `[c-*]` id cited in the
  Entry must resolve to a manifest Check id, and every Check `quote` must appear
  verbatim in the Entry. A dangling citation or a dropped quote is a failure, not a
  typo.
- `kind="novelty"` (D27): `data` is a literature-spike file; required for "first", "novel",
  "new", "unlike prior work".
- Uncovered fragments the owner has judged not to need a check are waived explicitly:
  `WAIVE = [Waive(fragment="<exact uncovered sentence text>", reason="<why no check is
  needed>")]`. The checker prints each waived fragment as `waived: <reason>`; a waiver
  whose fragment is no longer uncovered (Entry drifted, or a check now covers it) is
  stale and fails the run, so waivers cannot outlive their fragment.
- Only the worker writes checks; only the Decision step changes `status` and `audit_note`.
- `run_checks` must be all-pass and `coverage_scan` clean (or each uncovered sentence waived
  with a reason) before the result audit is launched.

- Setup facts quoted in the Entry (load, process counts, run windows, versions) get a
  `value` Check against the run's JSON, so transcription drift fails the checker, not the critic.
