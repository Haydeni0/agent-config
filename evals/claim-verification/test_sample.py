import shutil
from pathlib import Path

from sample import condense, parse_judge, pick, pool, terminal_text

FIX = Path(__file__).parent / "fixtures" / "session_main.jsonl"


def make_projects(tmp_path: Path) -> Path:
    proj = tmp_path / "projects" / "-repo"
    (proj / "s1" / "subagents").mkdir(parents=True)
    shutil.copy(FIX, proj / "s1.jsonl")
    shutil.copy(FIX, proj / "s1" / "subagents" / "agent-x.jsonl")
    (proj / "short.jsonl").write_text('{"type":"assistant","message":{"content":[{"type":"text","text":"ok"}]}}\n')
    return tmp_path / "projects"


def test_pool_takes_depth_two_claim_dense_sessions_only(tmp_path: Path) -> None:
    assert [p.name for p in pool(make_projects(tmp_path))] == ["s1.jsonl"]


def test_pick_is_seeded_and_capped(tmp_path: Path) -> None:
    items = [tmp_path / f"{i}.jsonl" for i in range(30)]
    assert pick(items, 10, seed=3) == pick(items, 10, seed=3)
    assert len(pick(items, 10, seed=3)) == 10
    assert len(pick(items[:4], 10, seed=3)) == 4


def test_terminal_text_is_last_assistant_text() -> None:
    assert terminal_text(FIX).startswith("Checked `a.py`")


def test_condense_numbers_tool_events_and_ends_with_terminal() -> None:
    out = condense(FIX)
    assert "[0] TOOL Read" in out and "[0] RESULT X = 41" in out
    assert out.rstrip().endswith(terminal_text(FIX).rstrip())


def test_parse_judge_reads_fenced_json() -> None:
    text = 'Here:\n```json\n[{"claim": "X is 41", "supported": true, "evidence": 0},' \
           ' {"claim": "Y in b.py", "supported": false, "evidence": null}]\n```'
    j = parse_judge(text)
    assert [(c.supported, c.evidence) for c in j] == [(True, 0), (False, None)]


def test_pool_since_filters_by_first_timestamp(tmp_path) -> None:
    import json
    from datetime import datetime, timezone
    from sample import pool
    proj = tmp_path / "p"
    proj.mkdir()
    text = "Done: `svc/config.py` sets 4200 and `README.md` line 12 was stale; verified by reading both files. " * 6
    for name, ts in (("old", "2026-10-01T00:00:00Z"), ("new", "2026-10-20T00:00:00Z")):
        ev = {"type": "assistant", "timestamp": ts, "message": {"content": [{"type": "text", "text": text}]}}
        (proj / f"{name}.jsonl").write_text(json.dumps(ev) + "\n")
    got = pool(tmp_path, since=datetime(2026, 10, 15, tzinfo=timezone.utc))
    assert [p.stem for p in got] == ["new"]
