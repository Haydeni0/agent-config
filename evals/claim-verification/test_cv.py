from pathlib import Path

from typer.testing import CliRunner

from cv import app
from model import Condition, Outcome, RunRecord
from summarize import dump_run


def test_summarize_writes_summary_md(tmp_path: Path) -> None:
    r = RunRecord("baseline", Condition.MCP, "S1", 0, 1, {}, Outcome.CAUGHT, 1, True, 10, 5, 0.0, 2, 1.0, "glm")
    (tmp_path / "runs.jsonl").write_text(dump_run(r) + "\n")
    res = CliRunner().invoke(app, ["summarize", str(tmp_path), "--header", "# B"])
    assert res.exit_code == 0, res.output
    assert "| baseline | mcp | S1 |" in (tmp_path / "summary.md").read_text()


def test_run_rejects_malformed_arm(tmp_path: Path) -> None:
    res = CliRunner().invoke(app, ["run", "--arm", "noequals", "--out", str(tmp_path), "--scratch", str(tmp_path)])
    assert res.exit_code == 2  # click usage error
