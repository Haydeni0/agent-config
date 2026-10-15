"""Tests for lab_commit.py: the provenance-commit gate.

Each test builds a throwaway git repo (lab dir inside) and runs the tool as a
subprocess with a controlled environment - the gate var present or absent - so
the gate itself is exercised exactly as a member session would.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
LAB_COMMIT = SCRIPTS / "lab_commit.py"
LAB_REL = ".agents/work/2026-10-15-lab-x"

E1_ENTRY = """# E1: Stage timing

## Brief

- **Question:** QR1
- **Tier:** headline

## Entry

- **Prediction outcomes:** P1 held
- **Result:** Stage B is 55% of end-to-end forward [c1].
- **Limits:** one shape, one seed.
- **Deviations from the brief:** none
- **Provenance:** command `uv run scratch/e1_stage.py`; `exp:` commit <SHA>; manifest `E1_manifest.py`
"""

EXPERIMENTS_MD = """# X Experiment log

## E1 (2026-10-15). First entry - done

E1 accepted content line one.
E1 content line two.

- **Provenance:** command `uv run scratch/e1.py`; `exp:` commit abc000; manifest `E1_manifest.py`

## E2 (2026-10-15). Second entry - done

- **Provenance:** command `uv run scratch/e2.py`; `exp:` commit <SHA>; manifest `E2_manifest.py`

## E3 (2026-10-15). Third entry - done

E3 draft content.
"""

REGEN_DROP_E1 = EXPERIMENTS_MD.replace(
    """## E1 (2026-10-15). First entry - done

E1 accepted content line one.
E1 content line two.

- **Provenance:** command `uv run scratch/e1.py`; `exp:` commit abc000; manifest `E1_manifest.py`

""",
    "",
)
REGEN_DROP_E3 = EXPERIMENTS_MD.replace(
    """## E3 (2026-10-15). Third entry - done

E3 draft content.
""",
    "",
)

FAIL_HOOK_CONFIG = """repos:
- repo: local
  hooks:
  - id: always-fail
    name: always-fail
    language: system
    entry: "false"
    pass_filenames: false
"""

# fails only when pre-commit hands it a results/ file, so it proves --data exclusion
NO_RESULTS_HOOK_CONFIG = """repos:
- repo: local
  hooks:
  - id: no-results
    name: results files are frozen
    language: system
    entry: "false"
    files: ^results/
"""


def _env(gate: bool) -> dict[str, str]:
    e = {k: v for k, v in os.environ.items() if k != "COMMIT_AUTHORISED"}
    e["GIT_CONFIG_GLOBAL"] = "/dev/null"  # fixture repos are machine-independent
    e["GIT_CONFIG_NOSYSTEM"] = "1"
    if gate:
        e["COMMIT_AUTHORISED"] = "1"
    return e


def _git(repo: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env or _env(True),
    )
    assert p.returncode == 0, p.stderr
    return p


def _status_md(states: dict[str, str]) -> str:
    out = [
        "E1 stream: entries audited; provenance commits pending.",
        "",
        "| by | milestone | state |",
        "|---|---|---|",
        "| 18:00 | page audited | [x] |",
        "",
        "| id | question | tier | state | budget | eta |",
        "|---|---|---|---|---|---|",
    ]
    out += [f"| {eid} | does it hold? | headline | {st} | 2 h | eta 18:00 |" for eid, st in states.items()]
    return "\n".join(out) + "\n"


def _audit_log(extra_row: str = "") -> str:
    return (
        "# Audit log\n\n"
        "| Time | Event | Experiment / page | Outcome | Detail | Evidence |\n"
        "|---|---|---|---|---|---|\n"
        f"| {datetime.now().strftime('%Y-%m-%d %H:%M')} | GATE | E1 | PASS | result audit | audit/E1.md |\n"
        f"{extra_row}"
    )


def _init_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "lab@test")
    _git(repo, "config", "user.name", "lab test")
    return repo, repo / LAB_REL


def _commit_scaffold(repo: Path, msg: str = "chore: lab scaffolding") -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", msg)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _make_single_lab(
    tmp_path: Path,
    *,
    decisions: str = "- D1 (2026-10-15). **E1 accepted.** P1 held; result audit PASS.",
    states: dict[str, str] | None = None,
) -> tuple[Path, Path, str]:
    """Skill-format lab: one file per experiment; the entry is untracked run output."""
    repo, lab = _init_repo(tmp_path)
    lab.mkdir(parents=True)
    (lab / "audit").mkdir()
    (lab / "decisions.md").write_text(f"# Decisions\n\n{decisions} Agent-picked.\n")
    (lab / "status.md").write_text(_status_md(states or {"E1": "[?]"}))
    (lab / "audit" / "log.md").write_text(_audit_log())
    head = _commit_scaffold(repo)
    # run artifacts, written after the scaffolding commit like a real member's output
    (lab / "experiments").mkdir()
    (lab / "experiments" / "E1.md").write_text(E1_ENTRY)
    (lab / "experiments" / "E1_manifest.py").write_text("CHECKS = []\n")
    (repo / "scratch").mkdir()
    (repo / "scratch" / "e1_stage.py").write_text("print('ran')\n")
    (repo / "results").mkdir()
    (repo / "results" / "e1.json").write_text('{"b_share": 0.55}\n')
    return repo, lab, head


def _make_shared_lab(tmp_path: Path, experiments_md: str) -> tuple[Path, Path, str]:
    """Pilot-format lab: one shared experiments.md, tracked in the scaffolding commit."""
    repo, lab = _init_repo(tmp_path)
    lab.mkdir(parents=True)
    (lab / "audit").mkdir()
    (lab / "decisions.md").write_text(
        "# Decisions\n\n- D1 (2026-10-15). **Result audited; entries corrected.** Agent-picked.\n"
    )
    (lab / "status.md").write_text(_status_md({"E1": "[x]", "E2": "[x]", "E3": "[ ]"}))
    (lab / "audit" / "log.md").write_text(_audit_log())
    (lab / "experiments.md").write_text(experiments_md)
    head = _commit_scaffold(repo)
    (repo / "scratch").mkdir()
    (repo / "scratch" / "e2.py").write_text("print('ran')\n")
    return repo, lab, head


def _run_tool(repo: Path, lab: Path, *cli: str, gate: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LAB_COMMIT), str(lab), *cli],
        cwd=repo,
        capture_output=True,
        text=True,
        env=_env(gate),
    )


def _e1_cli() -> list[str]:
    return [
        "--data",
        "results/e1.json",
        "--",
        f"{LAB_REL}/experiments/E1.md",
        f"{LAB_REL}/experiments/E1_manifest.py",
        "scratch/e1_stage.py",
        "results/e1.json",
    ]


def _head_subject(repo: Path) -> str:
    return _git(repo, "log", "-1", "--format=%s").stdout.strip()


def test_unaccepted_refuses(tmp_path):
    repo, lab, head = _make_single_lab(
        tmp_path, decisions="- D1 (2026-10-15). **E1 result audited.** Not decided yet."
    )
    p = _run_tool(repo, lab, "E1", *_e1_cli())
    assert p.returncode != 0
    assert "not marked accepted" in p.stderr
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == head


def test_commit_through_gate_writes_sha(tmp_path):
    repo, lab, head = _make_single_lab(tmp_path)
    p = _run_tool(repo, lab, "E1", *_e1_cli())
    assert p.returncode == 0, p.stderr
    assert _head_subject(repo) == "exp: E1 Stage timing"
    body = _git(repo, "log", "-1", "--format=%b").stdout
    assert "data files (hook-exempt): results/e1.json" in body
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert sha != head
    assert "results/e1.json" in _git(repo, "ls-tree", "--name-only", "HEAD", "results/").stdout
    entry = (lab / "experiments" / "E1.md").read_text()
    assert f"`exp:` commit {sha}" in entry  # SHA written into the Provenance line
    # the SHA edit is left for the next docs commit, so the entry stays dirty
    status = _git(repo, "status", "--porcelain").stdout
    assert f"M {LAB_REL}/experiments/E1.md" in status


def test_gate_absent_makes_no_commit(tmp_path):
    repo, lab, head = _make_single_lab(tmp_path)
    p = _run_tool(repo, lab, "E1", *_e1_cli(), gate=False)
    assert p.returncode != 0
    assert "COMMIT_AUTHORISED not set" in p.stderr
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == head
    staged = _git(repo, "diff", "--cached", "--name-only").stdout
    assert f"{LAB_REL}/experiments/E1.md" in staged  # paths stay staged for the re-run


def test_accepted_via_status_index(tmp_path):
    repo, lab, _ = _make_single_lab(
        tmp_path,
        decisions="- D1 (2026-10-15). **Result audited; entries corrected.** No D word accepts E1.",
        states={"E1": "[x]"},
    )
    p = _run_tool(repo, lab, "E1", "--", f"{LAB_REL}/experiments/E1.md")
    assert p.returncode == 0, p.stderr
    assert _head_subject(repo) == "exp: E1 Stage timing"


def test_deletion_of_accepted_entry_refused(tmp_path):
    repo, lab, head = _make_shared_lab(tmp_path, EXPERIMENTS_MD)
    (lab / "experiments.md").write_text(REGEN_DROP_E1)
    p = _run_tool(repo, lab, "E2", "--", f"{LAB_REL}/experiments.md", "scratch/e2.py")
    assert p.returncode != 0
    assert "silent-deletion" in p.stderr
    assert "E1" in p.stderr
    assert "E1 accepted content line one." in p.stderr  # says what would be deleted
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == head


def test_deletion_of_unaccepted_entry_allowed(tmp_path):
    repo, lab, _ = _make_shared_lab(tmp_path, EXPERIMENTS_MD)
    (lab / "experiments.md").write_text(REGEN_DROP_E3)
    p = _run_tool(repo, lab, "E2", "--", f"{LAB_REL}/experiments.md", "scratch/e2.py")
    assert p.returncode == 0, p.stderr
    assert _head_subject(repo) == "exp: E2 Second entry"
    committed = _git(repo, "show", f"HEAD:{LAB_REL}/experiments.md").stdout
    assert "E3 draft content" not in committed  # the unaccepted drop did go through
    assert "E1 accepted content line one." in committed  # the accepted entry survived
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert f"`exp:` commit {sha}" in (lab / "experiments.md").read_text()


def test_hook_failure_blocks_commit(tmp_path):
    repo, lab, head = _make_single_lab(tmp_path)
    (repo / ".pre-commit-config.yaml").write_text(FAIL_HOOK_CONFIG)
    p = _run_tool(repo, lab, "E1", *_e1_cli())
    assert p.returncode != 0
    assert "pre-commit hooks failed" in p.stderr
    assert "never --no-verify" in p.stderr
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == head


def test_data_files_exempt_from_hooks(tmp_path):
    repo, lab, _ = _make_single_lab(tmp_path)
    (repo / ".pre-commit-config.yaml").write_text(NO_RESULTS_HOOK_CONFIG)
    p = _run_tool(repo, lab, "E1", *_e1_cli())
    assert p.returncode == 0, p.stderr  # hook never sees results/e1.json
    assert _head_subject(repo) == "exp: E1 Stage timing"
    # without the exemption the same hook does fail on the data file
    p2 = _run_tool(repo, lab, "E1", "--", "results/e1.json")
    assert p2.returncode != 0
    assert "pre-commit hooks failed" in p2.stderr


def test_lint_failure_blocks_commit(tmp_path):
    repo, lab, head = _make_single_lab(tmp_path)
    (lab / "audit" / "log.md").write_text(
        _audit_log("| 2099-01-01 10:00 | GATE | E1 | PASS | projected | x |\n")
    )
    p = _run_tool(repo, lab, "E1", *_e1_cli())
    assert p.returncode != 0
    assert "lab lint failed" in p.stderr
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == head


def test_data_path_must_be_a_commit_path(tmp_path):
    repo, lab, _ = _make_single_lab(tmp_path)
    p = _run_tool(repo, lab, "E1", "--data", "results/e1.json", "--", f"{LAB_REL}/experiments/E1.md")
    assert p.returncode != 0
    assert "must also be commit paths" in p.stderr


def test_missing_entry_refuses(tmp_path):
    repo, lab, _ = _make_single_lab(
        tmp_path,
        decisions="- D1 (2026-10-15). **E9 accepted (E9-E9).**",
        states={"E1": "[?]", "E9": "[x]"},
    )
    p = _run_tool(repo, lab, "E9", "--", f"{LAB_REL}/experiments/E1.md")
    assert p.returncode != 0
    assert "no entry heading" in p.stderr
