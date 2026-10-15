"""Shared fixtures for the research-lab script tests: PATH shims for herdr/wt/sleep.

The shims live in fixtures/shims/ and record every call to $SHIM_LOG, so tests assert
what the scripts did to the outside world without touching a live herdr or wt.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

FIXTURES = Path(__file__).with_name("fixtures")


@pytest.fixture()
def shims(tmp_path, monkeypatch) -> SimpleNamespace:
    """PATH with herdr/wt/sleep shims first; exposes run(), log and the wt-list dir."""
    log = tmp_path / "shim.log"
    wt_json = tmp_path / "wt-list-json"
    wt_json.mkdir()
    monkeypatch.setenv("SHIM_LOG", str(log))
    monkeypatch.setenv("WT_LIST_JSON_DIR", str(wt_json))
    monkeypatch.setenv("HERDR_WORKSPACE_ID", "wA")
    monkeypatch.setenv("HERDR_PANE_ID", "wA:pZ")
    monkeypatch.setenv("HERDR_TEST_CALLER_PANE", "wA:pZ")
    monkeypatch.setenv("PATH", f"{FIXTURES / 'shims'}:{os.environ['PATH']}")

    def run(script: Path, args: list[str], *, cwd: Path | None = None,
            **extra_env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(script), *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            env={**os.environ, **extra_env},
        )

    return SimpleNamespace(run=run, log=log, wt_json=wt_json)
