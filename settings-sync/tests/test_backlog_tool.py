"""Tests for skills/backlog/backlog.py: serialized add/close lifecycle
(S1-S5), and skills/backlog/lint.py: structural lint (S6-S7). Fixtures are
tmpdir copies of the real file shapes - never the machine-local original
(it is gitignored state)."""

import importlib.util
import io
import re
import subprocess
import sys
import types
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKLOG = REPO_ROOT / "skills" / "backlog" / "backlog.py"
LINT = REPO_ROOT / "skills" / "backlog" / "lint.py"


@pytest.fixture(scope="module")
def backlog() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("backlog_tool", BACKLOG)
    module = importlib.util.module_from_spec(spec)
    sys.modules["backlog_tool"] = module
    spec.loader.exec_module(module)
    return module


def write_backlog(tmp_path: Path, body: str, done: str = "") -> Path:
    p = tmp_path / "backlog.md"
    p.write_text("# Backlog\n\n## Open\n\n" + body + "\n\n## Done\n\n" + done)
    return p


def run(backlog: types.ModuleType, p: Path, *args: str):
    from typer.testing import CliRunner

    result = CliRunner().invoke(backlog.app, [str(p), *args])
    assert result.exit_code == 0, result.output
    return result


def run_fails(backlog: types.ModuleType, p: Path, *args: str):
    from typer.testing import CliRunner

    result = CliRunner().invoke(backlog.app, [str(p), *args])
    assert result.exit_code != 0
    assert result.output.strip(), "a refusal must name what it saw"
    return result


def test_add_allocates_next_id_over_all_sections(tmp_path: Path, backlog: types.ModuleType):
    # #7 lives under Done: an Open-scoped max would allocate #4 (wrong)
    p = write_backlog(tmp_path, "- #3 [2026-11-01] three", done="- #7 [2026-11-01] seven")
    run(backlog, p, "add", "eight")
    text = p.read_text()
    assert f"- #8 [{date.today():%Y-%m-%d}] eight" in text.split("## Open")[1].split("## Done")[0]


def test_add_creates_canonical_file(tmp_path: Path, backlog: types.ModuleType):
    p = tmp_path / "backlog.md"
    run(backlog, p, "add", "first")
    assert "Deferred items for this project." in p.read_text()
    assert "- #1 [" in p.read_text()


def test_add_refuses_file_without_open_marker(tmp_path: Path, backlog: types.ModuleType):
    p = tmp_path / "backlog.md"
    p.write_text("# Backlog\n\n## Somewhere\n\n- #1 [2026-11-01] one\n")
    before = p.read_text()
    run_fails(backlog, p, "add", "two")
    assert p.read_text() == before


def test_close_moves_and_records(tmp_path: Path, backlog: types.ModuleType):
    p = write_backlog(tmp_path, "- #5 [2026-11-01] five")
    run(backlog, p, "close", "5", "the fix landed")
    text = p.read_text()
    assert "  -> DONE " in text and ": the fix landed" in text
    assert "- #5" in text.split("## Done")[1]
    assert "- #5" not in text.split("## Done")[0].split("## Open")[1]


def test_close_refuses_unknown_and_done(tmp_path: Path, backlog: types.ModuleType):
    p = write_backlog(tmp_path, "- #5 [2026-11-01] five")
    p.write_text(p.read_text().replace("## Done\n", "## Done\n\n- #6 [2026-11-01] six\n  -> DONE 2026-11-01: done\n"))
    before = p.read_text()
    assert run_fails(backlog, p, "close", "99", "x") is not None  # unknown id
    run_fails(backlog, p, "close", "6", "again")  # already in Done
    assert p.read_text() == before


def test_close_refuses_item_in_foreign_section(tmp_path: Path, backlog: types.ModuleType):
    p = tmp_path / "backlog.md"
    p.write_text(
        "# Backlog\n\n## Open\n\n- #4 [2026-11-01] four\n\n"
        "## Imported open items\n\n- #5 [2026-11-01] imported shape\n"
    )
    before = p.read_text()
    run_fails(backlog, p, "close", "5", "x")  # the only #5 sits outside Open/Done
    assert p.read_text() == before


def test_close_moves_multiline_block_intact(tmp_path: Path, backlog: types.ModuleType):
    # item #49's shape: blank lines INSIDE the block must not truncate it
    p = write_backlog(
        tmp_path,
        "- #49 [2026-10-15] long\n  first line\n\n  Gaps:\n  - (a) gap one\n\n  second tail\n",
    )
    run(backlog, p, "close", "49", "fixed")
    done = p.read_text().split("## Done")[1]
    for fragment in ("first line", "Gaps:", "gap one", "second tail"):
        assert fragment in done
    assert "first line" not in p.read_text().split("## Done")[0]


def test_close_creates_done_section_when_absent(tmp_path: Path, backlog: types.ModuleType):
    p = tmp_path / "backlog.md"
    p.write_text("# Backlog\n\n## Open\n\n- #5 [2026-11-01] five\n")
    run(backlog, p, "close", "5", "done deal")
    text = p.read_text()
    assert "## Done" in text
    assert "- #5" in text.split("## Done")[1]
    assert "## Done" in text.split("## Open")[1]  # created after Open


def test_concurrent_adds_serialize(tmp_path: Path, backlog: types.ModuleType):
    p = write_backlog(tmp_path, "- #1 [2026-11-01] one")
    script = tmp_path / "race.py"
    script.write_text(
        f"import subprocess, sys\n"
        f"subprocess.run([sys.executable, {str(BACKLOG)!r}, {str(p)!r}, 'add', sys.argv[1]], check=True)\n"
    )
    procs = [subprocess.Popen([sys.executable, str(script), f"racer-{i}"]) for i in range(2)]
    assert all(w.wait() == 0 for w in procs)
    text = p.read_text()
    ids = sorted(int(m) for m in re.findall(r"^- #(\d+) \[", text, re.M))
    assert len(ids) == len(set(ids)) == 3  # 1 original + 2 distinct racers


@pytest.fixture(scope="module")
def lint() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("backlog_lint", LINT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["backlog_lint"] = module
    spec.loader.exec_module(module)
    return module


def run_lint(lint: types.ModuleType, p: Path, *extra: str) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf), pytest.raises(SystemExit) as exc:
        lint.main([str(p), *extra])
    return exc.value.code, buf.getvalue()


def test_lint_clean_file_exits_zero(tmp_path: Path, lint: types.ModuleType):
    p = write_backlog(
        tmp_path,
        "- #1 [2026-11-01] one",
        done="- #2 [2026-11-01] two\n  -> DONE 2026-11-01: landed",
    )
    code, out = run_lint(lint, p)
    assert code == 0 and out == ""


def test_lint_flags_duplicate_ids_across_sections(tmp_path: Path, lint: types.ModuleType):
    p = write_backlog(
        tmp_path,
        "- #1 [2026-11-01] one",
        done="- #1 [2026-11-01] also one\n  -> DONE 2026-11-01: x",
    )
    code, out = run_lint(lint, p)
    assert code == 1
    assert "duplicate" in out and "#1" in out


def test_lint_flags_done_item_without_record(tmp_path: Path, lint: types.ModuleType):
    p = write_backlog(tmp_path, "- #1 [2026-11-01] one", done="- #2 [2026-11-01] bare")
    code, out = run_lint(lint, p)
    assert code == 1
    assert "#2" in out and "Done" in out


def test_lint_flags_done_record_under_open(tmp_path: Path, lint: types.ModuleType):
    p = write_backlog(
        tmp_path,
        "- #1 [2026-11-01] one\n  -> DONE 2026-11-01: early",
        done="- #2 [2026-11-01] two\n  -> DONE 2026-11-01: x",
    )
    code, out = run_lint(lint, p)
    assert code == 1
    assert "#1" in out and "Open" in out


def test_lint_accepts_closed_records_and_skips_foreign_sections(tmp_path: Path, lint: types.ModuleType):
    p = tmp_path / "backlog.md"
    p.write_text(
        "# Backlog\n\n## Open\n\n- #1 [2026-11-01] one\n\n"
        "## Imported legacy\n\n- #5 [2026-11-01] no record here\n  -> CLOSED 2026-11-01: fine\n\n"
        "## Done\n\n- #2 [2026-11-01] two\n  -> CLOSED 2026-11-01: done\n"
    )
    code, out = run_lint(lint, p)
    assert code == 0 and out == ""


def test_lint_requirements_dangling_pointer(tmp_path: Path, lint: types.ModuleType):
    p = write_backlog(
        tmp_path,
        "- #70 [2026-11-01] seventy",
        done="- #2 [2026-11-01] two\n  -> DONE 2026-11-01: x",
    )
    req = tmp_path / "requirements.md"
    req.write_text(
        "# Requirements\n\n"
        "| ID | Requirement | Verification |\n"
        "|---|---|---|\n"
        "| REQ-X-01 | Cites a missing backlog item #999 in a row. | manual |\n"
        "| REQ-X-02 | Cites an existing item (#70) - fine. | manual |\n"
        "| REQ-X-03 | Not a citation: anthropics/claude-code#74708. | manual |\n"
        "```markdown\n| REQ-X-04 | Fenced row citing #888 - skipped. | manual |\n```\n"
    )
    code, out = run_lint(lint, p, "--requirements", str(req))
    assert code == 1
    assert "#999" in out
    assert "#70" not in out and "#74708" not in out and "#888" not in out
