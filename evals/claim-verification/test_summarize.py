from pathlib import Path

from model import Condition, Outcome, RunRecord
from summarize import aggregate, dump_run, load_runs, render


def rec(scenario: str, outcome: Outcome, oracle: int = 0, recheck: bool = False, error: str | None = None) -> RunRecord:
    return RunRecord("baseline", Condition.MCP, scenario, 0, 1, {}, outcome, oracle, recheck, 100, 50, 0.0, 3, 1.0, "glm", error)


def test_aggregate_rates_exclude_errors_and_pool_all() -> None:
    cells = aggregate([
        rec("S1", Outcome.REPEATED), rec("S1", Outcome.CAUGHT, oracle=2, recheck=True),
        rec("S1", Outcome.ERROR, error="timeout"), rec("S2", Outcome.REPEATED),
    ])
    s1 = cells[("baseline", "mcp", "S1")]
    assert (s1.n, s1.errors, s1.repeated, s1.caught, s1.oracle, s1.recheck) == (2, 1, 0.5, 0.5, 0.5, 0.5)
    pooled = cells[("baseline", "mcp", "ALL")]
    assert (pooled.n, pooled.errors) == (3, 1)
    assert pooled.repeated == 2 / 3
    assert s1.mean_tokens == 150.0


def test_round_trip_jsonl(tmp_path: Path) -> None:
    r = rec("S3", Outcome.CAUGHT)
    p = tmp_path / "runs.jsonl"
    p.write_text(dump_run(r) + "\n")
    assert load_runs(p) == [r]


def test_render_has_one_row_per_cell() -> None:
    md = render(aggregate([rec("S1", Outcome.CAUGHT)]), header="# Baseline")
    assert md.startswith("# Baseline")
    assert "| baseline | mcp | S1 |" in md and "| baseline | mcp | ALL |" in md
