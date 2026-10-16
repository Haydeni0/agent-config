"""Lint for binding requirements contracts: duplicate IDs, citation resolution."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LINT = REPO / "skills" / "requirements" / "lint.py"

GOOD = """# Requirements

| ID | Requirement | Verification |
|---|---|---|
| REQ-A-01 | Alpha. | `test_alpha.py` (CI) |
| REQ-A-02 | Beta. | manual (given x, when y, then z) |
"""

DUPLICATE = GOOD + "| REQ-A-01 | Again. | manual (given x, when y, then z) |\n"
DANGLING = """# Requirements

| ID | Requirement | Verification |
|---|---|---|
| REQ-A-01 | Alpha. | `test_does_not_exist.py` (CI) |
"""


def run(tmp_path, text):
    contract = tmp_path / "requirements.md"
    contract.write_text(text)
    tests = tmp_path / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test_alpha.py").touch()
    return subprocess.run(
        [sys.executable, str(LINT), str(contract), str(tmp_path)],
        capture_output=True, text=True,
    )


def test_green_on_valid_contract(tmp_path):
    assert run(tmp_path, GOOD).returncode == 0


def test_duplicate_id_flagged(tmp_path):
    result = run(tmp_path, DUPLICATE)
    assert result.returncode == 1
    assert "REQ-A-01" in result.stdout and "duplicate" in result.stdout


def test_dangling_citation_flagged(tmp_path):
    result = run(tmp_path, DANGLING)
    assert result.returncode == 1
    assert "REQ-A-01" in result.stdout and "test_does_not_exist.py" in result.stdout


def test_real_contract_is_green():
    result = subprocess.run(
        [sys.executable, str(LINT), str(REPO / "docs" / "requirements.md"), str(REPO)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout
