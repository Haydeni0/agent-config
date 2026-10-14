"""Tests for scripts/check-packages.py (hyphenated, importlib) and package_states."""

import importlib.util
import re
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def load(name: str, script: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def tmp_work(tmp_path: Path) -> Path:
    w = tmp_path / "work"
    w.mkdir()
    return w


def make_package(work_dir: Path, slug: str, decisions: str = "", spec: str = "", plan: str = "") -> Path:
    d = work_dir / slug
    d.mkdir(parents=True)
    if decisions:
        (d / "decisions.md").write_text(decisions + "\n")
    if spec:
        (d / "spec.md").write_text(spec + "\n")
    if plan:
        (d / "plan.md").write_text(plan + "\n")
    return d


def findings(work_dir: Path) -> list[str]:
    lint = load("check_packages", "check-packages.py")
    return lint.lint_all(work_dir)


def test_valid_state_passes(tmp_work: Path) -> None:
    make_package(tmp_work, "p", decisions="state: grill\n\n# D\n")
    assert findings(tmp_work) == []


def test_malformed_state_line_fails(tmp_work: Path) -> None:
    make_package(tmp_work, "p", decisions="state: grill extra\n\n# D\n")
    fs = findings(tmp_work)
    assert any("malformed state" in f for f in fs)


def test_bad_heading_level_fails(tmp_work: Path) -> None:
    make_package(tmp_work, "p", decisions="state: complete\n\n### Outcome\n")
    fs = findings(tmp_work)
    assert any("Outcome" in f and "H2" in f for f in fs)


def test_fix_attempts_stray_position_fails(tmp_work: Path) -> None:
    make_package(tmp_work, "p", decisions="state: implement\nprose\nfix-attempts: 1\n")
    fs = findings(tmp_work)
    assert any("fix-attempts" in f and "directly after state" in f for f in fs)


def test_indented_state_line_fails(tmp_work: Path) -> None:
    make_package(tmp_work, "p", decisions="  state: banana\n\n# D\n")
    assert any("malformed state" in f for f in findings(tmp_work))


def test_unknown_state_fails(tmp_work: Path) -> None:
    make_package(tmp_work, "p", decisions="state: banana\n\n# D\n")
    fs = findings(tmp_work)
    assert len(fs) == 1 and "banana" in fs[0] and "state" in fs[0]


def test_absent_state_passes_legacy(tmp_work: Path) -> None:
    make_package(tmp_work, "p", decisions="# Decisions\n\n- D1. something\n", spec="# S\n\nReviewed: pass 1\n")
    assert findings(tmp_work) == []


def test_fix_attempts_valid_in_debug_state(tmp_work: Path) -> None:
    make_package(tmp_work, "p", decisions="state: hypothesis\nfix-attempts: 2\n\n# D\n")
    assert findings(tmp_work) == []


def test_fix_attempts_forbidden_in_non_debug_state(tmp_work: Path) -> None:
    make_package(tmp_work, "p", decisions="state: implement\nfix-attempts: 1\n\n# D\n")
    fs = findings(tmp_work)
    assert any("fix-attempts" in f and "forbidden" in f for f in fs)


def test_fix_attempts_required_in_debug_state(tmp_work: Path) -> None:
    make_package(tmp_work, "p", decisions="state: hypothesis\n\n# D\n")
    fs = findings(tmp_work)
    assert any("fix-attempts" in f and "required" in f for f in fs)


def test_fix_attempts_bad_syntax_fails(tmp_work: Path) -> None:
    make_package(tmp_work, "p", decisions="state: hypothesis\nfix-attempts: two\n\n# D\n")
    fs = findings(tmp_work)
    assert any("fix-attempts" in f for f in fs)


def test_malformed_reviewed_marker_fails(tmp_work: Path) -> None:
    make_package(tmp_work, "p", decisions="state: plan\n\n# D\n", spec="# S\n\nReviewed: pass\n")
    assert any("Reviewed" in f for f in findings(tmp_work))


def test_malformed_reviewed_word_fails(tmp_work: Path) -> None:
    make_package(tmp_work, "p", decisions="state: plan\n\n# D\n", spec="# S\n\nReviewed: banana 3\n")
    assert any("Reviewed" in f for f in findings(tmp_work))


def test_terminal_marker_position_checked(tmp_work: Path) -> None:
    make_package(tmp_work, "p", decisions="state: complete\n\n# D\n", plan="# P\n\nImplemented\n\nMore prose\n")
    fs = findings(tmp_work)
    assert any("Implemented" in f and "footer" in f for f in fs)


def test_reviewed_marker_position_checked(tmp_work: Path) -> None:
    make_package(tmp_work, "p", decisions="state: spec\n\n# D\n", spec="# S\n\nReviewed: pass 1\n\nprose after\n")
    fs = findings(tmp_work)
    assert any("Reviewed" in f and "footer" in f for f in fs)


def test_enum_single_source() -> None:
    states = load("package_states", "package_states.py")
    text = (REPO_ROOT / "skills" / "work-package" / "SKILL.md").read_text()
    m = re.search(r"^state: ([a-z0-9| -]+)$", text, re.M)
    assert m, "work-package SKILL.md missing canonical enum line"
    declared = {v.strip() for v in m.group(1).split("|")}
    assert declared == states.ALL_STATES
