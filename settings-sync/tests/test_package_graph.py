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


def test_t5_dangling_q_ref(graph: types.ModuleType, tmp_path: Path):
    decisions = (
        "state: grill\n\n## Open questions\n\n- Q1. First? Blocked by: Q7\n"
    )
    assert any("Q7" in f for f in check(graph, tmp_path, decisions=decisions))


def test_t5b_resolves_citation_closes(graph: types.ModuleType, tmp_path: Path):
    decisions = (
        "state: grill\n\n## Decisions\n\n- D1. **X.** Resolves Q7.\n\n"
        "## Open questions\n\n- Q1. First? Blocked by: Q7\n"
    )
    assert check(graph, tmp_path, decisions=decisions) == []


def test_t6_struck_q_closes(graph: types.ModuleType, tmp_path: Path):
    decisions = (
        "state: grill\n\n## Open questions\n\n"
        "- Q1. First? Blocked by: Q2\n- ~~Q2. Old?~~ Superseded.\n"
    )
    assert check(graph, tmp_path, decisions=decisions) == []


def test_t7_q_tags(graph: types.ModuleType, tmp_path: Path):
    bad = "state: grill\n\n## Open questions\n\n- Q1 [spike]. First?\n"
    assert any("spike" in f for f in check(graph, tmp_path, decisions=bad))
    good = "state: grill\n\n## Open questions\n\n- Q1 [research]. First?\n- Q2. Second?\n"
    assert check(graph, tmp_path, decisions=good) == []


def test_t9_duplicate_q_id(graph: types.ModuleType, tmp_path: Path):
    decisions = (
        "state: grill\n\n## Open questions\n\n- Q1. A?\n- Q1. B?\n"
    )
    assert any("duplicate" in f.lower() for f in check(graph, tmp_path, decisions=decisions))


def test_cross_file_ref_in_decisions(graph: types.ModuleType, tmp_path: Path):
    decisions = "state: grill\n\n## Open questions\n\n- Q1. A? Blocked by: Task 2\n"
    assert any("cross" in f.lower() for f in check(graph, tmp_path, decisions=decisions))


def test_q_cycle(graph: types.ModuleType, tmp_path: Path):
    decisions = (
        "state: grill\n\n## Open questions\n\n"
        "- Q1. A? Blocked by: Q2\n- Q2. B? Blocked by: Q1\n"
    )
    assert any("cycle" in f.lower() for f in check(graph, tmp_path, decisions=decisions))


def test_q_title_excludes_blocked_by_text(graph: types.ModuleType, tmp_path: Path):
    qs, resolved = graph.parse_decisions(
        "## Open questions\n\n- Q1. What is it? Blocked by: Q2\n- Q2. B?\n"
    )
    assert qs[0].title == "What is it?"
    assert qs[0].blocked_by == ["Q2"]


def test_f1_frontier_order_and_task_type_null(graph: types.ModuleType, tmp_path: Path):
    plan = (
        "### Task 1: A\n**Blocked by:** None\n- [x] s\n"
        "### Task 2: B\n**Blocked by:** Task 1\n- [ ] s\n"
        "### Task 3: C\n**Blocked by:** Task 2\n- [ ] s\n"
        "### Task 4: D\n**Blocked by:** None\n- [ ] s\n"
    )
    items = graph.frontier_pkg(make_pkg(tmp_path, plan=plan))
    assert [i["id"] for i in items] == ["Task 2", "Task 4"]
    assert all(i["type"] is None and i["kind"] == "task" for i in items)
    assert items[0]["blocked_by"] == ["Task 1"]
    assert items[0]["title"] == "B"


def test_f2_frontier_q_fields(graph: types.ModuleType, tmp_path: Path):
    decisions = (
        "state: grill\n\n## Decisions\n\n- D1. **X.** Resolves Q7.\n\n"
        "## Open questions\n\n- Q4. What next? Blocked by: Q7\n- Q9. Untagged?\n"
    )
    items = graph.frontier_pkg(make_pkg(tmp_path, decisions=decisions))
    by_id = {i["id"]: i for i in items}
    assert by_id["Q4"]["type"] == "grill" and by_id["Q4"]["kind"] == "q"
    assert by_id["Q9"]["type"] == "grill"
    assert all(set(i) == {"id", "kind", "type", "title", "blocked_by"} for i in items)


def test_f3_cli_frontier_finds_no_array(graph: types.ModuleType, tmp_path: Path):
    from typer.testing import CliRunner
    runner = CliRunner()
    pkg = make_pkg(tmp_path, plan="### Task 1: A\n**Blocked by:** Task 9\n- [ ] s\n")
    result = runner.invoke(graph.app, ["frontier", str(pkg)])
    assert result.exit_code != 0
    assert result.stdout.strip() == ""


def test_f4_cli_frontier_json(graph: types.ModuleType, tmp_path: Path):
    from typer.testing import CliRunner
    runner = CliRunner()
    plan = (
        "### Task 1: A\n**Blocked by:** None\n- [x] s\n"
        "### Task 2: B\n**Blocked by:** Task 1\n- [ ] s\n"
    )
    result = runner.invoke(graph.app, ["frontier", str(make_pkg(tmp_path, plan=plan))])
    assert result.exit_code == 0
    items = json.loads(result.stdout)
    assert items[0]["id"] == "Task 2"


def test_typed_q_in_frontier(graph: types.ModuleType, tmp_path: Path):
    decisions = (
        "state: grill\n\n## Open questions\n\n- Q1 [research]. External fact? Blocked by: Q9\n"
        "- Q2 [prototype]. How should it look?\n- ~~Q9. Old?~~ Done.\n"
    )
    items = graph.frontier_pkg(make_pkg(tmp_path, decisions=decisions))
    by_id = {i["id"]: i for i in items}
    assert by_id["Q1"]["type"] == "research"
    assert by_id["Q2"]["type"] == "prototype"


def test_frontier_title_first_sentence(graph: types.ModuleType, tmp_path: Path):
    decisions = "state: grill\n\n## Open questions\n\n- Q1. How does X work? More context here.\n"
    items = graph.frontier_pkg(make_pkg(tmp_path, decisions=decisions))
    assert items[0]["title"] == "How does X work?"
