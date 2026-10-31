"""Tests for skills/work-package/graph.py: dependency edges and frontier
(scenarios T1-T9, F1-F4, I1; REQ-SKILLS-14 graph amendment, REQ-SKILLS-26)."""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GRAPH = REPO_ROOT / "skills" / "work-package" / "graph.py"


@pytest.fixture(scope="module")
def graph() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("wp_graph", GRAPH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["wp_graph"] = module
    spec.loader.exec_module(module)
    return module


def make_pkg(tmp_path: Path, plan: str = "", decisions: str = "") -> Path:
    make_pkg.n += 1
    pkg = tmp_path / f"pkg{make_pkg.n}"
    pkg.mkdir()
    if plan:
        (pkg / "plan.md").write_text(plan + "\n")
    if decisions:
        (pkg / "decisions.md").write_text(decisions + "\n")
    return pkg


make_pkg.n = 0


def check(graph: types.ModuleType, tmp_path: Path, plan: str = "", decisions: str = "") -> list[str]:
    return graph.check_pkg(make_pkg(tmp_path, plan, decisions))


def test_t1_dangling_task_ref(graph: types.ModuleType, tmp_path: Path):
    findings = check(graph, tmp_path, plan=(
        "### Task 1: A\n**Blocked by:** Task 9\n- [ ] step\n"
    ))
    assert any("Task 9" in f for f in findings)


def test_t2_cycles(graph: types.ModuleType, tmp_path: Path):
    plan = (
        "### Task 1: A\n**Blocked by:** Task 2\n- [ ] s\n"
        "### Task 2: B\n**Blocked by:** Task 1\n- [ ] s\n"
    )
    assert any("cycle" in f.lower() for f in check(graph, tmp_path, plan=plan))
    self_loop = "### Task 1: A\n**Blocked by:** Task 1\n- [ ] s\n"
    assert any("cycle" in f.lower() for f in check(graph, tmp_path, plan=self_loop))


def test_t3_closed_task_with_open_blocker(graph: types.ModuleType, tmp_path: Path):
    plan = (
        "### Task 1: A\n**Blocked by:** None\n- [x] s\n"
        "### Task 2: B\n**Blocked by:** Task 3\n- [x] s\n"
        "### Task 3: C\n**Blocked by:** None\n- [ ] s\n"
    )
    findings = check(graph, tmp_path, plan=plan)
    assert any("Task 2" in f and "Task 3" in f for f in findings)


def test_t4_partial_opt_in_and_zero_boxes(graph: types.ModuleType, tmp_path: Path):
    partial = (
        "### Task 1: A\n**Blocked by:** None\n- [ ] s\n"
        "### Task 2: B\n- [ ] s\n"
    )
    assert any("Task 2" in f and "Blocked by" in f for f in check(graph, tmp_path, plan=partial))
    zero = (
        "### Task 1: A\n**Blocked by:** None\n- [ ] s\n"
        "### Task 2: B\n**Blocked by:** Task 1\n"
    )
    assert any("Task 2" in f and "checkbox" in f for f in check(graph, tmp_path, plan=zero))


def test_t4b_legacy_plan_passes(graph: types.ModuleType, tmp_path: Path):
    plan = "### Task 1: A\n- [ ] s\n### Task 2: B\n- [x] s\n"
    assert check(graph, tmp_path, plan=plan) == []


def test_t9_duplicate_task_id(graph: types.ModuleType, tmp_path: Path):
    plan = (
        "### Task 1: A\n**Blocked by:** None\n- [ ] s\n"
        "### Task 1: B\n**Blocked by:** None\n- [ ] s\n"
    )
    assert any("duplicate" in f.lower() for f in check(graph, tmp_path, plan=plan))


def test_t8_cross_file_ref_in_plan(graph: types.ModuleType, tmp_path: Path):
    plan = "### Task 1: A\n**Blocked by:** Q1\n- [ ] s\n"
    assert any("cross" in f.lower() for f in check(graph, tmp_path, plan=plan))


def test_unparseable_ref_is_finding(graph: types.ModuleType, tmp_path: Path):
    plan = "### Task 1: A\n**Blocked by:** Taskk 2\n- [ ] s\n"
    assert any("Taskk 2" in f for f in check(graph, tmp_path, plan=plan))


def test_fenced_content_ignored(graph: types.ModuleType, tmp_path: Path):
    plan = (
        "### Task 1: A\n**Blocked by:** None\n- [ ] s\n"
        "```markdown\n### Task 2: fake\n**Blocked by:** Task 99\n```\n"
    )
    assert check(graph, tmp_path, plan=plan) == []
