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
| REQ-A-03 | Gamma. | manual (given x, when y, then z); `test_alpha.py` (CI) |
"""

DUPLICATE = GOOD + "| REQ-A-01 | Again. | manual (given x, when y, then z) |\n"
DANGLING = """# Requirements

| ID | Requirement | Verification |
|---|---|---|
| REQ-A-01 | Alpha. | `test_does_not_exist.py` (CI) |
"""
# A manual span must not exempt the row's other citations.
MIXED = """# Requirements

| ID | Requirement | Verification |
|---|---|---|
| REQ-A-01 | Alpha. | manual (given x, when y, then z); `test_missing.py` (CI) |
"""
# Non-REQ ID schemes must lint too.
OTHER_SCHEME = """# Requirements

| ID | Requirement | Verification |
|---|---|---|
| FR-1 | Alpha. | `test_missing.py` (CI) |
| FR-1 | Duplicate. | manual (given x, when y, then z) |
"""
NO_ROWS = "# Notes\n\nNo table here.\n"


def run(tmp_path, text, *args):
    contract = tmp_path / "requirements.md"
    contract.write_text(text)
    tests = tmp_path / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test_alpha.py").touch()
    return subprocess.run(
        [sys.executable, str(LINT), str(contract), *args],
        capture_output=True, text=True, cwd=tmp_path,
    )


def test_green_on_valid_contract(tmp_path):
    assert run(tmp_path, GOOD).returncode == 0


def test_cwd_is_default_root(tmp_path):
    assert run(tmp_path, GOOD, str(tmp_path)).returncode == 0


def test_duplicate_id_flagged_with_line(tmp_path):
    result = run(tmp_path, DUPLICATE)
    assert result.returncode == 1
    assert "REQ-A-01" in result.stdout and "duplicate" in result.stdout
    assert "line 5" in result.stdout


def test_dangling_citation_flagged(tmp_path):
    result = run(tmp_path, DANGLING)
    assert result.returncode == 1
    assert "REQ-A-01" in result.stdout and "test_does_not_exist.py" in result.stdout


def test_manual_span_does_not_exempt_citations(tmp_path):
    result = run(tmp_path, MIXED)
    assert result.returncode == 1
    assert "test_missing.py" in result.stdout


def test_non_req_id_scheme_lints(tmp_path):
    result = run(tmp_path, OTHER_SCHEME)
    assert result.returncode == 1
    assert "FR-1" in result.stdout and "duplicate" in result.stdout
    assert "test_missing.py" in result.stdout


def test_no_rows_is_a_loud_error(tmp_path):
    result = run(tmp_path, NO_ROWS)
    assert result.returncode == 2
    assert "no contract rows parsed" in result.stderr


def test_real_contract_is_green():
    result = subprocess.run(
        [sys.executable, str(LINT), "docs/requirements.md"],
        capture_output=True, text=True, cwd=REPO,
    )
    assert result.returncode == 0, result.stdout
