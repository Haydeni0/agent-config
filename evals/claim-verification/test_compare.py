from compare import fisher_one_sided, oracle_counts, pooled, select
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


def _orec(arm: str, scenario: str, outcome: Outcome, calls: int, cond: Condition = Condition.MCP) -> RunRecord:
    return RunRecord(arm, cond, scenario, 0, 0, {}, outcome, calls, False, 0, 0, 0.0, 0, 0.0, None)


def test_pooled_and_oracle_filter_scenarios() -> None:
    recs = [_orec("A1", "S2", Outcome.REPEATED, 0), _orec("A1", "S5", Outcome.REPEATED, 1),
            _orec("A1", "S1", Outcome.CAUGHT, 1), _orec("A1", "S1", Outcome.CAUGHT, 0, Condition.NO_MCP)]
    core = frozenset({"S1", "S2", "S3", "S4"})
    assert pooled(recs, core) == {"A1": (1, 3)}
    assert oracle_counts(recs, core) == {"A1": (1, 2)}


def test_select_oracle_tie_break() -> None:
    counts = {"baseline": (9, 40), "A1": (2, 40), "A2": (2, 40)}
    oracle = {"A1": (18, 20), "A2": (8, 20)}
    s = select(counts, "baseline", "A1", ["A2"], oracle)
    assert s.chosen == "A2" and s.p_oracle["A2"] < 0.05
    counts["A2"] = (3, 40)
    assert select(counts, "baseline", "A1", ["A2"], oracle).chosen == "A1"
