from pathlib import Path

import dataclasses

from typer.testing import CliRunner

from cv import app
from model import Condition, Outcome, RunRecord
from scenarios import generate
from summarize import dump_run, load_runs

S2_MISREAD_ARTIFACT = (
    "# Status\n\n## Do tests pass?\n\nNo. Ran `uv run pytest`: **1 failed, 4 passed**.\n\n"
    "- `ScaleTest::test_scale_unit` FAILS: `scale(1)` returns 1234, test expects 4321 (`tests/test_ops.py:8`).\n"
    "- Other 4 tests pass (`scale(n) == n * 1234`).\n"
)


def _transcript_jsonl(final: str) -> str:
    return (
        '{"type": "system", "subtype": "init", "model": "glm", "tools": [], "mcp_servers": []}\n'
        '{"type": "result", "result": ' + f'"{final}", "num_turns": 1, "usage": {{"input_tokens": 1, "output_tokens": 1}}}}\n'
    )


def _record(arm: str, cond: Condition, sid: str, rep: int, seed: int, truth: dict, outcome: Outcome,
            tpath: str | None) -> RunRecord:
    return RunRecord(arm, cond, sid, rep, seed, truth, outcome, 1, True, 10, 5, 0.0, 2, 1.0, "glm", None, tpath)


def _write_results(out: Path) -> list[RunRecord]:
    tdir = out / "transcripts"
    tdir.mkdir(parents=True)
    s2 = generate("S2", 7, out / "ws-s2")
    s1 = generate("S1", 11, out / "ws-s1")
    s3 = generate("S3", 3, out / "ws-s3")
    truth2 = {k: v for k, v in s2.truth.items() if not k.startswith("_")}
    truth1 = {k: v for k, v in s1.truth.items() if not k.startswith("_")}
    truth3 = {k: v for k, v in s3.truth.items() if not k.startswith("_")}
    (tdir / "x-mcp-S2-0.artifact").write_text(S2_MISREAD_ARTIFACT)
    (tdir / "x-mcp-S2-0.jsonl").write_text(_transcript_jsonl("unused"))
    (tdir / "x-mcp-S1-0.jsonl").write_text(
        _transcript_jsonl(f"The default timeout is {s1.truth['false']} ms and it retries {s1.truth['retries']} times.")
    )
    recs = [
        _record("x", Condition.MCP, "S2", 0, 7, truth2, Outcome.REPEATED, str(tdir / "x-mcp-S2-0.jsonl")),
        _record("x", Condition.MCP, "S1", 0, 11, truth1, Outcome.REPEATED, str(tdir / "x-mcp-S1-0.jsonl")),
        _record("x", Condition.MCP, "S3", 0, 3, truth3, Outcome.ERROR, None),
    ]
    (out / "runs.jsonl").write_text("".join(dump_run(r) + "\n" for r in recs))
    return recs


def test_rescore_reclassifies_saved_runs_and_keeps_orig(tmp_path: Path) -> None:
    _write_results(tmp_path)
    res = CliRunner().invoke(app, ["rescore", str(tmp_path)])
    assert res.exit_code == 0, res.output
    orig = load_runs(tmp_path / "runs.orig.jsonl")
    assert [r.outcome for r in orig] == [Outcome.REPEATED, Outcome.REPEATED, Outcome.ERROR]
    runs = {r.scenario: r for r in load_runs(tmp_path / "runs.jsonl")}
    # D15: the S2 misread (reports the failing test) flips repeated -> caught
    assert runs["S2"].outcome is Outcome.CAUGHT
    # the S1 relay is untouched by D15 and keeps its recorded outcome; text came from the saved transcript
    assert runs["S1"].outcome is Outcome.REPEATED
    # the error run is never reclassified
    assert runs["S3"].outcome is Outcome.ERROR
    # oracle and recheck are not recomputed
    assert all((r.oracle_calls, r.recheck) == (1, True) for r in runs.values())


def test_rescore_rereads_orig_not_current_runs(tmp_path: Path) -> None:
    _write_results(tmp_path)
    assert CliRunner().invoke(app, ["rescore", str(tmp_path)]).exit_code == 0
    (tmp_path / "runs.jsonl").write_text("")  # a later bad write must not poison the rescore
    res = CliRunner().invoke(app, ["rescore", str(tmp_path)])
    assert res.exit_code == 0, res.output
    assert [r.outcome for r in load_runs(tmp_path / "runs.jsonl")] == [Outcome.CAUGHT, Outcome.REPEATED, Outcome.ERROR]
    # runs.orig.jsonl is never overwritten once it exists
    assert [r.outcome for r in load_runs(tmp_path / "runs.orig.jsonl")] == [Outcome.REPEATED] * 2 + [Outcome.ERROR]


def test_rescore_raises_on_truth_mismatch(tmp_path: Path) -> None:
    recs = _write_results(tmp_path)
    bad = dataclasses.replace(recs[0], truth=dict(recs[0].truth, factor=recs[0].truth["factor"] + 1))
    (tmp_path / "runs.jsonl").write_text(dump_run(bad) + "\n")
    res = CliRunner().invoke(app, ["rescore", str(tmp_path)])
    assert res.exit_code != 0
    assert "regenerated truth" in str(res.exception)
