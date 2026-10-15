from compare import fisher_one_sided, pooled, select
from model import Condition, Outcome, RunRecord


def _rec(arm: str, outcome: Outcome) -> RunRecord:
    return RunRecord(arm, Condition.MCP, "S2", 0, 0, {}, outcome, 0, False, 0, 0, 0.0, 0, 0.0, None)


def test_fisher_matches_reference_values() -> None:
    assert round(fisher_one_sided(9, 40, 2, 40), 4) == 0.0238
    assert round(fisher_one_sided(9, 40, 3, 40), 4) == 0.0574
    assert fisher_one_sided(5, 10, 5, 10) > 0.5


def test_pooled_excludes_errors() -> None:
    recs = [_rec("A1", Outcome.REPEATED), _rec("A1", Outcome.CAUGHT), _rec("A1", Outcome.ERROR)]
    assert pooled(recs) == {"A1": (1, 2)}


def test_select_keeps_default_unless_challenger_significantly_better() -> None:
    counts = {"baseline": (9, 40), "A1": (2, 40), "A2": (1, 40), "A3": (6, 40)}
    s = select(counts, "baseline", "A1", ["A2", "A3"])
    assert s.chosen == "A1" and s.beats_baseline
    counts["A2"] = (0, 40)
    counts["A1"] = (8, 40)
    s = select(counts, "baseline", "A1", ["A2", "A3"])
    assert s.chosen == "A2" and s.beats_baseline


def test_select_reports_no_win_over_baseline() -> None:
    s = select({"baseline": (9, 40), "A1": (5, 40)}, "baseline", "A1", [])
    assert s.chosen == "A1" and not s.beats_baseline
