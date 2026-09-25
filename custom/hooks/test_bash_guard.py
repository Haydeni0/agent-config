"""Exercise the Claude command hook as a subprocess against shared policy cases.

Denied commands return native deny JSON; passing commands leave stdout empty.
Payload edge cases exercise the compatibility entry point's JSON handling.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent / "check-bash-guard.sh"
CASES = json.loads((Path(__file__).resolve().parents[2] / "hooks/tests/fixtures/command-cases.json").read_text())
GROUPS = {g["name"]: g for g in CASES["groups"]}


def _bash() -> str:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is required")
    assert bash is not None
    return bash


def _require_jq() -> None:
    if shutil.which("jq") is None:
        pytest.skip("jq is required")


def _run(command: str) -> subprocess.CompletedProcess[str]:
    _require_jq()
    payload = json.dumps({"tool_input": {"command": command}})
    # No check=True: a non-zero exit (e.g. bug under set -euo pipefail) should
    # surface as an assertion failure, not a swallowed CalledProcessError.
    result = subprocess.run(
        [_bash(), str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"hook exited {result.returncode}; stderr={result.stderr!r}, "
        f"stdout={result.stdout!r}"
    )
    return result


def _assert_allowed(result: subprocess.CompletedProcess[str]) -> None:
    assert result.stdout == "", f"expected no decision, got: {result.stdout!r}"


def _assert_denied(result: subprocess.CompletedProcess[str], needle: str) -> None:
    assert result.stdout, "expected a deny decision on stdout"
    decision = json.loads(result.stdout)
    hook_output = decision["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "deny"
    assert needle in hook_output["permissionDecisionReason"], (
        f"expected {needle!r} in reason, got {hook_output['permissionDecisionReason']!r}"
    )


# -- shared corpus (parametrized from command-cases.json) -------------
# Add a command to the JSON and it flows into both this test and the opencode
# plugin test. The functions below are thin parametrize-and-assert wrappers;
# the corpus is the source of truth for what's blocked/allowed.

def _group(name: str) -> dict:
    return GROUPS[name]


def _cases(name: str) -> list[str]:
    return _group(name)["commands"]


def _needle(name: str) -> str:
    return _group(name)["needle"]


for _g in CASES["groups"]:
    _expect = _g["expect"]
    _name = _g["name"]
    _needle_val = _g.get("needle", "")
    if _expect == "deny":
        def _make_denier(group_name, group_needle):
            def _test(command):
                _assert_denied(_run(command), group_needle)
            _test.__name__ = f"test_{group_name}"
            return pytest.mark.parametrize("command", GROUPS[group_name]["commands"])(_test)
        globals()[f"test_{_name}"] = _make_denier(_name, _needle_val)
    else:
        def _make_allower(group_name):
            def _test(command):
                _assert_allowed(_run(command))
            _test.__name__ = f"test_{group_name}"
            return pytest.mark.parametrize("command", GROUPS[group_name]["commands"])(_test)
        globals()[f"test_{_name}"] = _make_allower(_name)


# -- payload edge cases (harness-specific: tests jq/JSON parsing) ----------
# No opencode equivalent - the opencode plugin receives output.args.command
# directly from the framework, no stdin JSON to parse.


@pytest.mark.parametrize(
    "payload",
    [
        {"tool_input": {}},
        {"tool_input": {"command": ""}},
        {"tool_input": {"command": "ls -la"}},
        {"tool_input": {"command": "echo hello"}},
        {"tool_input": {"command": "aws s3 ls s3://bucket/"}},
    ],
)
def test_edge_payloads(payload: dict) -> None:
    _require_jq()
    result = subprocess.run(
        [_bash(), str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "", f"expected silence for {payload!r}, got {result.stdout!r}"
