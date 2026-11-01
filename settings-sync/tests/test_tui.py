import json
import pathlib

from settings_sync.actions import MergedConfig, Mode, Status
from settings_sync.config import build_tui
from settings_sync.executor import execute
from settings_sync.merging import JsonCodec
from settings_sync.ownership import OwnershipStore

TUI_SCHEMA = "https://opencode.ai/tui.json"


def apply_tui(target: pathlib.Path, base: pathlib.Path, mode: Mode):
    store = OwnershipStore()
    store.load(mode)
    return execute([MergedConfig(target, JsonCodec(), build_tui(base))], mode, store)[0]


def test_creates_tui_from_base(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode" / "tui.json"
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({"theme": "tokyonight"}))
    target = tmp_path / "config" / "opencode" / "tui.json"

    outcome = apply_tui(target, base, Mode.APPLY)

    assert outcome.status == Status.MERGED
    written = json.loads(target.read_text())
    assert written["theme"] == "tokyonight"
    assert written["$schema"] == TUI_SCHEMA


def test_creates_empty_tui_when_base_missing(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode" / "tui.json"
    target = tmp_path / "config" / "opencode" / "tui.json"

    outcome = apply_tui(target, base, Mode.APPLY)

    assert outcome.status == Status.MERGED
    written = json.loads(target.read_text())
    assert written == {"$schema": TUI_SCHEMA}
