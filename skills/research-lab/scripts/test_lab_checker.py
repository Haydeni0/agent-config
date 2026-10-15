"""Deterministic-gate tests for lab_checker.py on the critic-bench E1 variants.

Fixtures are copies of the planted-fault bench from research-lab-pilot
(tests/critic-bench: 12 variants of the audited T1 E1 entry, one fault each,
3 byte-identical controls; key in the pilot repo). Expected split, from the
bench's results.md:

- faults a, b, d, f, g, h fail the deterministic checker (a via the
  exact-rounding rule; b, d, f via the cross-index quote rule; g via the
  cross-index citation rule; h via the coverage scan);
- faults c, e, i are prose/structural and PASS the checker - they are the
  critic's job. These tests pin that boundary so a checker change that
  silently widens (or narrows) it is caught.

The control entry's 4 uncovered number sentences are the original entry's
owner-waived baseline (the bench's gate.txt): the control manifest carries
them as ``WAIVE`` entries, so the control runs the full gate green, while the
``_gate`` tests below assert the raw coverage scan still reports exactly
those 4 before waivers.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import lab_checker as lc  # noqa: E402

FIXTURES = SCRIPTS / "fixtures"
MANIFEST = FIXTURES / "E1_manifest.py"
MANIFEST_A = FIXTURES / "E1_manifest_a.py"  # fault-a variant: c-b-share-bf16 quote 97.79
BASELINE_UNCOVERED = 4  # owner-waived fragments of the original audited entry


def _load_checks(manifest: Path) -> list[lc.Check]:
    namespace = {"Check": lc.Check, "CHECKS": [], "__file__": str(manifest)}
    exec(manifest.read_text(), namespace)
    return namespace["CHECKS"]


def _gate(manifest: Path, entry: Path) -> tuple[list[lc.Failure], list[lc.Failure], list[str]]:
    """(check failures, cross-index failures, uncovered sentences)."""
    checks = _load_checks(manifest)
    check_failures = lc.run_checks(checks, quiet=True)
    cross_failures = lc.cross_index(checks, entry)
    uncovered = lc.coverage_scan(entry, [c.quote for c in checks], section="## Entry")
    return check_failures, cross_failures, uncovered


def _entry(name: str) -> Path:
    return FIXTURES / f"E1_{name}.md"


def test_control_clean_modulo_waived_baseline():
    check_failures, cross_failures, uncovered = _gate(MANIFEST, _entry("control"))
    assert check_failures == []
    assert cross_failures == []
    assert len(uncovered) == BASELINE_UNCOVERED


def test_fault_a_rounding_drift():
    # prose 97.79 vs computed 97.9677 at 2dp; manifest quote matches the mutated prose,
    # so only the exact-rounding rule can catch it
    check_failures, cross_failures, uncovered = _gate(MANIFEST_A, _entry("a"))
    assert len(check_failures) == 1
    f = check_failures[0]
    assert (f.check_id, f.rule) == ("c-b-share-bf16", "R5 value/unit")
    assert "rounding 2dp" in f.detail and "97.79" in f.detail
    assert cross_failures == []
    assert len(uncovered) == BASELINE_UNCOVERED


def test_fault_b_gross_drift_stale_manifest():
    # entry says 12.6%, manifest quote still checks 0.42 (matching the JSON), so
    # run_checks passes; the quote no longer appears verbatim -> cross-index catches
    check_failures, cross_failures, uncovered = _gate(MANIFEST, _entry("b"))
    assert check_failures == []
    assert [(f.check_id, f.rule) for f in cross_failures] == [("c-sum-bf16", "cross-index quote")]
    assert any("12.6" in s for s in uncovered)
    assert len(uncovered) == BASELINE_UNCOVERED + 1


def test_fault_d_dropped_prediction_outcome():
    # the P3 outcome sentence (and with it the c-p3 quote) was removed from the Entry
    check_failures, cross_failures, uncovered = _gate(MANIFEST, _entry("d"))
    assert check_failures == []
    assert [(f.check_id, f.rule) for f in cross_failures] == [("c-p3", "cross-index quote")]
    assert len(uncovered) == BASELINE_UNCOVERED


def test_fault_f_median_reported_as_mean():
    # "median is 204.91 ms" became "mean is 204.91 ms": the value is the median
    # (JSON mean 205.42), and the c-e2e-bf16 quote is gone from the Entry
    check_failures, cross_failures, uncovered = _gate(MANIFEST, _entry("f"))
    assert check_failures == []
    assert (cross_failures[0].check_id, cross_failures[0].rule) == (
        "c-e2e-bf16",
        "cross-index quote",
    )
    assert any("mean is 204.91" in s for s in uncovered)
    assert len(uncovered) == BASELINE_UNCOVERED + 1


def test_fault_g_dangling_citation():
    # [c-max-nbrs] was retyped to [c-max-nb]: cited id resolves to no manifest Check
    check_failures, cross_failures, uncovered = _gate(MANIFEST, _entry("g"))
    assert check_failures == []
    assert len(cross_failures) == 1
    f = cross_failures[0]
    assert (f.check_id, f.rule) == ("c-max-nb", "cross-index citation")
    assert "Entry line" in f.detail  # reported with the Entry line
    assert len(uncovered) == BASELINE_UNCOVERED


def test_fault_h_effect_below_noise():
    # appended "further 3.6% saving" clause: below the IQR, but a number-bearing
    # sentence no quote covers, so the coverage scan flags it
    check_failures, cross_failures, uncovered = _gate(MANIFEST, _entry("h"))
    assert check_failures == []
    assert cross_failures == []
    assert any("6% saving" in s for s in uncovered)  # "3." ends the prior fragment
    assert len(uncovered) == BASELINE_UNCOVERED + 1


# critic-only faults: digit-free scope/confound prose (c, i) and code-path labels (e).
# The deterministic checker must not fire on these - they are the result-audit
# critic's job (bench: caught only by R2/R5/R7).
def test_critic_only_faults_pass_the_checker():
    for name in ("c", "e", "i"):
        check_failures, cross_failures, uncovered = _gate(MANIFEST, _entry(name))
        assert check_failures == [], name
        assert cross_failures == [], name
        assert len(uncovered) == BASELINE_UNCOVERED, name


def _run_main(argv: list[str], monkeypatch, capsys) -> tuple[int, str]:
    monkeypatch.setattr(sys, "argv", ["lab_checker.py", *argv])
    rc = lc.main()
    return rc, capsys.readouterr().out


def test_main_exit_codes(monkeypatch, capsys, tmp_path):
    # a fully green manifest: check passes, cross-index clean, coverage clean -> 0
    data = tmp_path / "d.json"
    data.write_text('{"loss": 0.25}')
    manifest = tmp_path / "m.py"
    manifest.write_text(
        "from lab_checker import Check\n"
        "CHECKS = [Check(id='c-loss', quote='loss is 0.25', "
        f"data={str(data)!r}, expr=\"d['loss']\", kind='value', rounding=2)]\n"
    )
    entry = tmp_path / "e.md"
    entry.write_text("## Brief\n\n## Entry\n\nFinal loss is 0.25 [c-loss].\n")
    assert _run_main([str(manifest), str(entry)], monkeypatch, capsys)[0] == 0

    # dangling citation -> nonzero
    entry.write_text("## Entry\n\nFinal loss is 0.25 [c-loss] [c-typo].\n")
    assert _run_main([str(manifest), str(entry)], monkeypatch, capsys)[0] == 1

    # uncovered number sentence -> nonzero (owner must waive or add a check)
    entry.write_text("## Entry\n\nFinal loss is 0.25 [c-loss]. Early loss was 0.9.\n")
    assert _run_main([str(manifest), str(entry)], monkeypatch, capsys)[0] == 1

    # a waiver for that exact fragment covers it -> 0, printed as 'waived: <reason>'
    manifest.write_text(
        "from lab_checker import Check, Waive\n"
        "CHECKS = [Check(id='c-loss', quote='loss is 0.25', "
        f"data={str(data)!r}, expr=\"d['loss']\", kind='value', rounding=2)]\n"
        "WAIVE = [Waive(fragment='Early loss was 0.9.', reason='transitional value')]\n"
    )
    rc, out = _run_main([str(manifest), str(entry)], monkeypatch, capsys)
    assert rc == 0
    assert "waived: transitional value" in out

    # stale waiver: the fragment is gone from the Entry -> failure
    entry.write_text("## Entry\n\nFinal loss is 0.25 [c-loss].\n")
    rc, out = _run_main([str(manifest), str(entry)], monkeypatch, capsys)
    assert rc == 1
    assert "stale waiver" in out


def test_control_exits_zero_with_baseline_waivers(monkeypatch, capsys):
    # the control manifest carries the 4 owner-waived baseline fragments, so a
    # clean entry runs the full gate green end to end
    rc, out = _run_main(
        [str(MANIFEST), str(_entry("control"))], monkeypatch, capsys
    )
    assert rc == 0
    assert out.count("waived:") == BASELINE_UNCOVERED


def test_novelty_kind_carried_not_evaluated(tmp_path):
    # D27: data is a literature-spike file; existence is checked, values are not
    spike = tmp_path / "lit.md"
    spike.write_text("# spike\n")
    c = lc.Check(id="c-n", quote="first at this scale", data=str(spike), expr="", kind="novelty")
    assert lc.run_checks([c], quiet=True) == []
    missing = lc.Check(
        id="c-n", quote="first at this scale", data=str(tmp_path / "gone.md"), expr="", kind="novelty"
    )
    failures = lc.run_checks([missing], quiet=True)
    assert failures[0].check_id == "c-n" and "not found" in failures[0].detail
