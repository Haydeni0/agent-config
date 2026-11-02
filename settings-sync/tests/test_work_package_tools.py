"""Tests for skills/work-package/advance.py: guarded marker and state writes
(S10-S12), and skills/work-package/sections.py (S8-S9). Fixtures are tmpdir
packages - never the machine-local package store (it is gitignored state)."""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ADVANCE = REPO_ROOT / "skills" / "work-package" / "advance.py"
SECTIONS = REPO_ROOT / "skills" / "work-package" / "sections.py"


@pytest.fixture(scope="module")
def advance() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("wp_advance", ADVANCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["wp_advance"] = module
    spec.loader.exec_module(module)
    return module


def make_pkg(tmp_path: Path, decisions: str = "", spec: str = "", plan: str = "") -> Path:
    make_pkg.n += 1
    pkg = tmp_path / f"pkg{make_pkg.n}"
    pkg.mkdir()
    for name, text in (("decisions.md", decisions), ("spec.md", spec), ("plan.md", plan)):
        if text:
            (pkg / name).write_text(text)
    return pkg


make_pkg.n = 0


def run(tool: types.ModuleType, pkg: Path, *args: str):
    from typer.testing import CliRunner

    return CliRunner().invoke(tool.app, [str(pkg), *args])


def ok(tool: types.ModuleType, pkg: Path, *args: str):
    result = run(tool, pkg, *args)
    assert result.exit_code == 0, result.output
    return result


def refused(tool: types.ModuleType, pkg: Path, *args: str):
    result = run(tool, pkg, *args)
    assert result.exit_code != 0
    assert result.output.strip(), "a refusal must name what it saw"
    return result


def test_s10_review_appends_pass_one_on_empty(advance: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(tmp_path, decisions="state: spec\n", spec="The spec body.\n")
    ok(advance, pkg, "--review", "pass", "--artifact", "spec")
    assert (pkg / "spec.md").read_text().rstrip("\n").endswith("Reviewed: pass 1")


def test_s10_review_enforces_round_continuity(advance: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(
        tmp_path,
        decisions="state: spec\n",
        spec="Body.\n\nReviewed: fail 1\nReviewed: fail 2\n",
    )
    ok(advance, pkg, "--review", "pass", "--artifact", "spec")
    assert (pkg / "spec.md").read_text().rstrip("\n").endswith("Reviewed: pass 3")


def test_s10_review_refuses_gap_no_write(advance: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(
        tmp_path,
        decisions="state: spec\n",
        spec="Body.\n\nReviewed: fail 1\nReviewed: fail 3\n",
    )
    before = (pkg / "spec.md").read_text()
    result = refused(advance, pkg, "--review", "pass", "--artifact", "spec")
    assert "fail 3" in result.output
    assert (pkg / "spec.md").read_text() == before


def test_s10_review_refuses_marker_outside_footer(advance: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(
        tmp_path,
        decisions="state: spec\n",
        spec="Reviewed: pass 1\n\nprose between markers\n\nReviewed: pass 2\n",
    )
    before = (pkg / "spec.md").read_text()
    refused(advance, pkg, "--review", "pass", "--artifact", "spec")
    assert (pkg / "spec.md").read_text() == before


def test_s10_review_refuses_content_after_markers(advance: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(
        tmp_path,
        decisions="state: spec\n",
        spec="Body.\n\nReviewed: pass 1\n\ntrailing prose\n",
    )
    before = (pkg / "spec.md").read_text()
    refused(advance, pkg, "--review", "pass", "--artifact", "spec")
    assert (pkg / "spec.md").read_text() == before


def test_s10_review_tolerates_implemented_in_plan_footer(advance: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(
        tmp_path,
        decisions="state: plan\n",
        plan="Plan body.\n\nReviewed: fail 1\nImplemented\n",
    )
    ok(advance, pkg, "--review", "pass", "--artifact", "plan")
    text = (pkg / "plan.md").read_text()
    assert "Reviewed: pass 2" in text
    assert text.count("\nImplemented\n") == 1


def test_s10_review_requires_the_named_artifact(advance: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(tmp_path, decisions="state: spec\n")  # no spec.md
    refused(advance, pkg, "--review", "pass", "--artifact", "spec")


def test_s11_state_rewrite_on_exact_match(advance: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(tmp_path, decisions="state: spec\n\n## Decisions\n\n- D1. A.\n")
    ok(advance, pkg, "--expect-state", "spec", "--set-state", "plan")
    text = (pkg / "decisions.md").read_text()
    assert text.split("\n")[0] == "state: plan"
    assert "- D1. A." in text


def test_s11_state_mismatch_refuses_no_write(advance: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(tmp_path, decisions="state: grill\n\n## Decisions\n")
    before = (pkg / "decisions.md").read_text()
    result = refused(advance, pkg, "--expect-state", "spec", "--set-state", "plan")
    assert "grill" in result.output and "spec" in result.output
    assert (pkg / "decisions.md").read_text() == before


def test_s11_state_absent_reports_none(advance: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(tmp_path, decisions="## Decisions\n\n- D1. A.\n")
    result = refused(advance, pkg, "--expect-state", "spec", "--set-state", "plan")
    assert "<none>" in result.output


def test_s12_invalid_transition_refused(advance: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(tmp_path, decisions="state: spec\n")
    refused(advance, pkg, "--expect-state", "spec", "--set-state", "implement")
    refused(advance, pkg, "--expect-state", "spec", "--set-state", "bogus")


def test_s12_implemented_appends_once(advance: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(tmp_path, decisions="state: implement\n", plan="Plan body.\n")
    ok(advance, pkg, "--implemented")
    assert (pkg / "plan.md").read_text().rstrip("\n").endswith("Implemented")
    before = (pkg / "plan.md").read_text()
    refused(advance, pkg, "--implemented")
    assert (pkg / "plan.md").read_text() == before


def test_flags_compose_review_and_state(advance: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(tmp_path, decisions="state: spec\n", spec="Body.\n")
    ok(advance, pkg, "--review", "pass", "--artifact", "spec",
       "--expect-state", "spec", "--set-state", "plan")
    assert (pkg / "spec.md").read_text().rstrip("\n").endswith("Reviewed: pass 1")
    assert (pkg / "decisions.md").read_text().split("\n")[0] == "state: plan"


def test_composed_failure_writes_nothing(advance: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(tmp_path, decisions="state: grill\n", spec="Body.\n")
    before_spec = (pkg / "spec.md").read_text()
    before_dec = (pkg / "decisions.md").read_text()
    refused(advance, pkg, "--review", "pass", "--artifact", "spec",
            "--expect-state", "spec", "--set-state", "plan")
    assert (pkg / "spec.md").read_text() == before_spec
    assert (pkg / "decisions.md").read_text() == before_dec


def test_flag_pairs_required_together(advance: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(tmp_path, decisions="state: spec\n")
    refused(advance, pkg, "--review", "pass")        # --artifact missing
    refused(advance, pkg, "--artifact", "spec")      # --review missing
    refused(advance, pkg, "--expect-state", "spec")  # --set-state missing
    refused(advance, pkg, "--set-state", "plan")     # --expect-state missing
    refused(advance, pkg)                            # nothing requested
