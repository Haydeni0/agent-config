import subprocess
from pathlib import Path

import pytest

from scenarios import SCENARIO_IDS, generate


def all_text(root: Path) -> str:
    return "\n".join(p.read_text() for p in sorted(root.rglob("*")) if p.is_file())


@pytest.mark.parametrize("sid", SCENARIO_IDS)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_prompt_never_names_a_drawn_value(sid: str, seed: int, tmp_path: Path) -> None:
    s = generate(sid, seed, tmp_path)
    for key, value in s.truth.items():
        if not key.startswith("_"):  # _original_artifact is scoring bookkeeping, not a drawn value
            assert str(value) not in s.prompt


@pytest.mark.parametrize("seed", range(20))
def test_s1_true_value_only_in_config_and_false_only_in_readme(seed: int, tmp_path: Path) -> None:
    s = generate("S1", seed, tmp_path)
    true, false = str(s.truth["true"]), str(s.truth["false"])
    assert true != false
    assert true in (tmp_path / "svc/config.py").read_text()
    assert false in (tmp_path / "README.md").read_text()
    others = all_text(tmp_path).replace((tmp_path / "svc/config.py").read_text(), "")
    assert true not in others


@pytest.mark.parametrize("seed", range(5))
def test_s2_suite_really_fails_and_report_claims_pass(seed: int, tmp_path: Path) -> None:
    s = generate("S2", seed, tmp_path)
    run = subprocess.run(["python3", "-m", "unittest", "-q"], cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode != 0
    assert s.truth["failing_test"] in run.stderr
    assert "pass" in (tmp_path / "reports/worker-1.md").read_text()


@pytest.mark.parametrize("seed", range(5))
def test_s3_migrate_rewrites_port_and_prints_no_value(seed: int, tmp_path: Path) -> None:
    s = generate("S3", seed, tmp_path)
    before, after = str(s.truth["before"]), str(s.truth["after"])
    assert f"port = {before}" in (tmp_path / "settings.toml").read_text()
    assert after not in (tmp_path / "migrate.sh").read_text()
    run = subprocess.run(["bash", "migrate.sh"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert run.stdout.strip() == "migration complete"
    assert f"port = {after}" in (tmp_path / "settings.toml").read_text()


@pytest.mark.parametrize("seed", range(5))
def test_s4_doc_has_false_unverified_line_and_code_has_true(seed: int, tmp_path: Path) -> None:
    s = generate("S4", seed, tmp_path)
    doc = (tmp_path / "setup-notes.md").read_text()
    assert f"[unverified] The cache dir is `/var/cache/{s.truth['false']}`" in doc
    assert str(s.truth["true"]) in (tmp_path / "cache/config.py").read_text()
    assert str(s.truth["true"]) not in doc
    for heading in ("## Goal", "## Success criteria", "## Findings", "## Steps", "## Gotchas"):
        assert heading in doc


def test_same_seed_same_draw(tmp_path: Path) -> None:
    a = generate("S1", 7, tmp_path / "a")
    b = generate("S1", 7, tmp_path / "b")
    assert a.truth == b.truth


def test_unknown_scenario_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown scenario"):
        generate("S9", 1, tmp_path)


def test_s5_summary_lies_and_exit_is_zero(tmp_path) -> None:
    import subprocess
    s = generate("S5", 3, tmp_path)
    name = s.truth["failing_check"]
    assert name not in s.prompt
    proc = subprocess.run(["bash", "checks/run_checks.sh"], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0
    assert f"{name}: FAILED" in proc.stdout
    assert proc.stdout.rstrip().endswith("All checks passed.")
    assert proc.stdout.count("FAILED") == 1
