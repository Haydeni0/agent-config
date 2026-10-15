import json
from pathlib import Path

import pytest

from model import Condition, Outcome, RunRecord
from revise import MAX_FAILURES, brief, extract_revision

SKILL = "---\nname: claim-verification\nlayer: worker\ndeps: []\n\n# claim-verification\n\nBody text.\n"


def _transcript(path: Path, text: str) -> str:
    ev = {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}
    path.write_text(json.dumps(ev) + "\n")
    return str(path)


def _rec(scenario: str, outcome: Outcome, tpath: str, rep: int = 0) -> RunRecord:
    return RunRecord("A1", Condition.MCP, scenario, rep, 0, {}, outcome, 0, False, 0, 0, 0.0, 0, 0.0, None, None, tpath)


def test_brief_never_shows_holdout(tmp_path) -> None:
    recs = [_rec("S2", Outcome.REPEATED, _transcript(tmp_path / "a.jsonl", "relayed tests pass")),
            _rec("S5", Outcome.REPEATED, _transcript(tmp_path / "b.jsonl", "HOLDOUT-MARKER"))]
    b = brief(recs, "A1", SKILL)
    assert "relayed tests pass" in b and "HOLDOUT-MARKER" not in b and "S5" not in b


def test_brief_caps_failures(tmp_path) -> None:
    recs = [_rec("S2", Outcome.REPEATED, _transcript(tmp_path / f"{i}.jsonl", f"run-{i}"), i) for i in range(10)]
    b = brief(recs, "A1", SKILL)
    assert sum(f"run-{i}" in b for i in range(10)) == MAX_FAILURES


def test_extract_revision_checks_fence_pins_and_growth() -> None:
    ok = "why\n\n````markdown\n" + SKILL.replace("Body text.", "Better body.") + "````\n"
    assert "Better body." in extract_revision(ok, SKILL)
    with pytest.raises(ValueError, match="fence"):
        extract_revision("no fence here", SKILL)
    with pytest.raises(ValueError, match="pinned"):
        extract_revision("````markdown\n" + SKILL.replace("layer: worker", "layer: orchestrator") + "````", SKILL)
    with pytest.raises(ValueError, match="grows"):
        extract_revision("````markdown\n" + SKILL + "x" * len(SKILL) + "\n````", SKILL)
