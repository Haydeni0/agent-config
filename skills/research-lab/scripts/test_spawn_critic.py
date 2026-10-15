"""spawn-critic.sh: prompt from template + paths only (D17), ring-back, then spawn."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).with_name("spawn-critic.sh")
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

PROFILE = """# PI profile

## Staffing

| role | launcher | model | effort |
|---|---|---|---|
| default | test-agent | small | medium |
| critic | test-agent | | |
"""


def make_lab(tmp_path: Path) -> SimpleNamespace:
    """A minimal lab: experiment files, data, and a code repo with one commit."""
    lab = tmp_path / "lab"
    for sub in ("audit", "experiments", "data", "scratch/critic-e1", "packs/kernels"):
        (lab / sub).mkdir(parents=True)
    (lab / "experiments" / "E1.md").write_text("# E1\n\nBrief and entry.\n")
    (lab / "experiments" / "E1_manifest.py").write_text("# manifest\n")
    (lab / "data" / "a.json").write_text("{}\n")
    (lab / "data" / "b.json").write_text("{}\n")
    (lab / "false-findings.md").write_text("| pattern | how detected | domain |\n|---|---|---|\n")

    code = tmp_path / "code"
    code.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=code, check=True, capture_output=True)
    (code / "e1.py").write_text("print('e1')\n")
    subprocess.run(["git", "add", "."], cwd=code, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "e1"],
                   cwd=code, check=True, capture_output=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=code, check=True,
                          capture_output=True, text=True).stdout.strip()
    return SimpleNamespace(lab=lab, code=code, sha=sha)


def audit_args(lab: Path, code: Path, sha: str, verdict: Path) -> list[str]:
    return [
        "critic-result-audit", str(verdict), "t1-critic-e1", "--",
        f"experiment_path={lab}/experiments/E1.md",
        f"manifest_path={lab}/experiments/E1_manifest.py",
        f"data_paths={lab}/data/a.json,{lab}/data/b.json",
        f"code_paths={code}/e1.py",
        f"exp_sha={sha}",
        f"scratch_dir={lab}/scratch/critic-e1",
        f"false_findings_path={lab}/false-findings.md",
        f"pack_path={lab}/packs/kernels",
    ]


@pytest.fixture()
def profile(tmp_path: Path) -> str:
    p = tmp_path / "pi-profile.md"
    p.write_text(PROFILE)
    return str(p)


def run(shims, args: list[str], profile: str) -> subprocess.CompletedProcess[str]:
    return shims.run(SCRIPT, args, RESEARCH_LAB_PROFILE=profile)


def test_full_run_fills_paths_and_spawns(tmp_path, shims, profile):
    lab = make_lab(tmp_path)
    verdict = lab.lab / "audit" / "E1-verdict.md"

    result = run(shims, audit_args(lab.lab, lab.code, lab.sha, verdict), profile)

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == str(lab.lab / "audit" / "E1-verdict-spawn.md")
    assert lines[1] == "wA:pT1"
    text = Path(lines[0]).read_text()
    assert not re.search(r"\{[a-z_]+\}", text), "unfilled template key left in the prompt"
    assert f"at commit {lab.sha}" in text
    assert f"{lab.lab}/data/a.json,{lab.lab}/data/b.json" in text
    assert f'herdr agent prompt wA:pZ "done: {verdict}"' in text
    log = shims.log.read_text()
    assert "agent rename wA:pT1 t1-critic-e1" in log
    assert "herdr agent prompt wA:pT1 You are a fresh" in log


def test_refuses_value_that_is_not_a_path(tmp_path, shims, profile):
    lab = make_lab(tmp_path)
    verdict = lab.lab / "audit" / "E1-verdict.md"
    args = audit_args(lab.lab, lab.code, lab.sha, verdict)
    bad = f"experiment_path={tmp_path / 'nope' / 'E1.md'}"
    args[args.index(f"experiment_path={lab.lab}/experiments/E1.md")] = bad

    result = run(shims, args, profile)

    assert result.returncode == 1
    assert "not an existing path" in result.stderr
    assert list((lab.lab / "audit").iterdir()) == [], "spawn prompt written despite refusal"


def test_refuses_verdict_that_already_exists(tmp_path, shims, profile):
    lab = make_lab(tmp_path)
    verdict = lab.lab / "audit" / "E1-verdict.md"
    verdict.write_text("PASS\n")

    result = run(shims, audit_args(lab.lab, lab.code, lab.sha, verdict), profile)

    assert result.returncode == 1
    assert "already exists" in result.stderr


def test_refuses_unfilled_template_key(tmp_path, shims, profile):
    lab = make_lab(tmp_path)
    verdict = lab.lab / "audit" / "E1-verdict.md"
    args = [a for a in audit_args(lab.lab, lab.code, lab.sha, verdict)
            if not a.startswith("scratch_dir=")]

    result = run(shims, args, profile)

    assert result.returncode == 1
    assert "not filled: scratch_dir" in result.stderr


def test_refuses_bad_sha(tmp_path, shims, profile):
    lab = make_lab(tmp_path)
    verdict = lab.lab / "audit" / "E1-verdict.md"
    args = [a if not a.startswith("exp_sha=") else "exp_sha=deadbee"
            for a in audit_args(lab.lab, lab.code, lab.sha, verdict)]

    result = run(shims, args, profile)

    assert result.returncode == 1
    assert "not a commit" in result.stderr


def test_prior_round_adds_recheck_line(tmp_path, shims, profile):
    lab = make_lab(tmp_path)
    prior = lab.lab / "audit" / "E1-verdict-r1.md"
    prior.write_text("PASS-WITH-FIXES\n")
    verdict = lab.lab / "audit" / "E1-verdict-r2.md"
    args = ["critic-result-audit", str(verdict), "t1-critic-e1", "--prior", str(prior), "--"]
    args += audit_args(lab.lab, lab.code, lab.sha, verdict)[4:]

    result = run(shims, args, profile)

    assert result.returncode == 0, result.stderr
    text = Path(result.stdout.splitlines()[0]).read_text()
    assert f"Prior round verdict: {prior}" in text
    assert "then audit afresh" in text


def test_prior_must_exist(tmp_path, shims, profile):
    lab = make_lab(tmp_path)
    verdict = lab.lab / "audit" / "E1-verdict.md"
    args = audit_args(lab.lab, lab.code, lab.sha, verdict)
    args[3:3] = ["--prior", str(tmp_path / "nope-r1.md")]

    result = run(shims, args, profile)

    assert result.returncode == 1
    assert "--prior verdict" in result.stderr


def test_refuses_unknown_template(tmp_path, shims, profile):
    lab = make_lab(tmp_path)
    verdict = lab.lab / "audit" / "E1-verdict.md"
    args = audit_args(lab.lab, lab.code, lab.sha, verdict)
    args[0] = "critic-nope"

    result = run(shims, args, profile)

    assert result.returncode == 1
    assert "not found" in result.stderr


def test_design_review_template(tmp_path, shims, profile):
    lab = make_lab(tmp_path)
    (lab.lab / "policy.md").write_text("# Policy\n")
    verdict = lab.lab / "audit" / "E1-design-verdict.md"
    args = [
        str(TEMPLATES / "critic-design-review.md"), str(verdict), "t1-critic-e1", "--",
        f"brief_path={lab.lab}/experiments/E1.md",
        f"code_paths={lab.code}/e1.py",
        f"policy_path={lab.lab}/policy.md",
        f"false_findings_path={lab.lab}/false-findings.md",
        f"pack_path={lab.lab}/packs/kernels",
    ]

    result = run(shims, args, profile)

    assert result.returncode == 0, result.stderr
    text = Path(result.stdout.splitlines()[0]).read_text()
    assert "D8 Domain pack checklist" in text
    assert not re.search(r"\{[a-z_]+\}", text)
