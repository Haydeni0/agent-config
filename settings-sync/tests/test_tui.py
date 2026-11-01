import json
import pathlib

import pytest

from settings_sync.config import sync_tui
from settings_sync.actions import Status

TUI_SCHEMA = "https://opencode.ai/tui.json"


def test_creates_tui_from_base(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode" / "tui.json"
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({"theme": "tokyonight"}))
    target = tmp_path / "config" / "opencode" / "tui.json"

    outcome = sync_tui(target, base)

    assert outcome.status == Status.CREATED
    written = json.loads(target.read_text())
    assert written["theme"] == "tokyonight"
    assert written["$schema"] == TUI_SCHEMA


def test_creates_empty_tui_when_base_missing(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode" / "tui.json"
    target = tmp_path / "config" / "opencode" / "tui.json"

    outcome = sync_tui(target, base)

    assert outcome.status == Status.CREATED
    written = json.loads(target.read_text())
    assert written == {"$schema": TUI_SCHEMA}
