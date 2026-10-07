"""Tests for scripts/check-skills.py (hyphenated module, loaded via importlib)."""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check-skills.py"


@pytest.fixture()
def check_module():
    spec = importlib.util.spec_from_file_location("check_skills", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_skill(skills_dir: Path, name: str, body: str, *, layer: str | None = None, deps: list[str] | None = None) -> None:
    d = skills_dir / name
    d.mkdir(parents=True)
    fm = ["---", f"name: {name}", "description: test skill"]
    if layer:
        fm.append(f"layer: {layer}")
    if deps is not None:
        fm.append("deps: [" + ", ".join(deps) + "]")
    fm.append("---")
    (d / "SKILL.md").write_text("\n".join(fm) + "\n\n" + body + "\n")


def run_check(check_module, tmp_path: Path):
    return check_module.check(tmp_path / "skills", tmp_path)


def test_deps_unknown_name_fails(check_module, tmp_path):
    make_skill(tmp_path / "skills", "alpha", "body", deps=["no-such-skill"])
    failures, _ = run_check(check_module, tmp_path)
    assert any("alpha" in f and "no-such-skill" in f for f in failures)


def test_deps_self_reference_fails(check_module, tmp_path):
    make_skill(tmp_path / "skills", "alpha", "body", deps=["alpha"])
    failures, _ = run_check(check_module, tmp_path)
    assert any("alpha" in f and "self" in f.lower() for f in failures)


def test_worker_dep_on_orchestrator_fails(check_module, tmp_path):
    make_skill(tmp_path / "skills", "orch-skill", "body", layer="orchestrator")
    make_skill(tmp_path / "skills", "worker-skill", "body", layer="worker", deps=["orch-skill"])
    failures, _ = run_check(check_module, tmp_path)
    assert any("worker-skill" in f and "orch-skill" in f for f in failures)


def test_worker_dep_on_worker_passes(check_module, tmp_path):
    make_skill(tmp_path / "skills", "a-worker", "body", layer="worker")
    make_skill(tmp_path / "skills", "b-worker", "body", layer="worker", deps=["a-worker"])
    failures, _ = run_check(check_module, tmp_path)
    assert not any("deps" in f for f in failures)


def test_worker_body_citing_plan_package_passes(check_module, tmp_path):
    make_skill(tmp_path / "skills", "plan-package", "layout contract")
    make_skill(tmp_path / "skills", "a-worker", "load the plan-package skill first", layer="worker")
    failures, _ = run_check(check_module, tmp_path)
    assert not any("package" in f for f in failures)


def test_worker_body_bare_package_word_fails(check_module, tmp_path):
    make_skill(tmp_path / "skills", "a-worker", "the package layout is x", layer="worker")
    failures, _ = run_check(check_module, tmp_path)
    assert any("package" in f for f in failures)


def test_plan_package_exempt_from_package_word(check_module, tmp_path):
    make_skill(tmp_path / "skills", "plan-package", "the package layout table lives here", layer="worker")
    failures, _ = run_check(check_module, tmp_path)
    assert not any("package" in f for f in failures)
