import json
import pathlib

import pytest

from settings_sync.actions import MergedConfig, Mode, Status
from settings_sync.config import build_config
from settings_sync.executor import execute
from settings_sync.merging import JsonCodec, strip_jsonc
from settings_sync.ownership import OwnershipStore


def merged_for(target: pathlib.Path, base: pathlib.Path) -> MergedConfig:
    legacy = target.with_suffix(".jsonc")
    migrate = None
    if legacy.is_file():
        migrate = json.loads(strip_jsonc(legacy.read_text()))
        if not isinstance(migrate, dict):
            raise ValueError("legacy JSON must be an object")
    return MergedConfig(target, JsonCodec(), build_config(base), migrate=migrate,
                        remove_after=legacy if migrate is not None else None)


def apply_merged(action: MergedConfig, mode: Mode):
    store = OwnershipStore()
    store.load(mode)
    return execute([action], mode, store)[0]


def test_creates_config_from_base(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode.json"
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({"model": "anthropic/claude-sonnet-4-5"}))
    target = tmp_path / "config" / "opencode" / "opencode.json"

    outcome = apply_merged(merged_for(target, base), Mode.APPLY)

    assert outcome.status == Status.MERGED
    written = json.loads(target.read_text())
    assert written["model"] == "anthropic/claude-sonnet-4-5"
    assert written["$schema"] == "https://opencode.ai/config.json"


def test_creates_with_empty_base_when_missing(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode.json"
    target = tmp_path / "config" / "opencode" / "opencode.json"

    outcome = apply_merged(merged_for(target, base), Mode.APPLY)

    assert outcome.status == Status.MERGED
    written = json.loads(target.read_text())
    assert written == {"$schema": "https://opencode.ai/config.json"}


def test_unchanged_when_identical(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode.json"
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({"model": "x"}))
    target = tmp_path / "config" / "opencode" / "opencode.json"
    apply_merged(merged_for(target, base), Mode.APPLY)

    outcome = apply_merged(merged_for(target, base), Mode.APPLY)

    assert outcome.status == Status.UNCHANGED


def test_updates_declared_keys_without_force(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode.json"
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({"model": "new"}))
    target = tmp_path / "config" / "opencode" / "opencode.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"model": "hand-edited"}))

    outcome = apply_merged(merged_for(target, base), Mode.APPLY)

    assert outcome.status == Status.MERGED
    assert json.loads(target.read_text())["model"] == "new"


def test_force_overwrites_diverging_target(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode.json"
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({"model": "new"}))
    target = tmp_path / "config" / "opencode" / "opencode.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"model": "hand-edited"}))

    outcome = apply_merged(merged_for(target, base), Mode.FORCE)

    assert outcome.status == Status.MERGED
    assert json.loads(target.read_text())["model"] == "new"


def test_dry_run_does_not_write(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode.json"
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({"model": "x"}))
    target = tmp_path / "config" / "opencode" / "opencode.json"

    outcome = apply_merged(merged_for(target, base), Mode.DRY_RUN)

    assert outcome.status == Status.WOULD_CREATE
    assert not target.exists()


def test_migrates_jsonc_into_opencode_json(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode.json"
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({"model": "x"}))
    target_dir = tmp_path / "config" / "opencode"
    target_dir.mkdir(parents=True)
    jsonc = target_dir / "opencode.jsonc"
    jsonc.write_text('{\n  // my config\n  "$schema": "https://opencode.ai/config.json",\n  "model": "y",\n}\n')
    target = target_dir / "opencode.json"

    outcome = apply_merged(merged_for(target, base), Mode.APPLY)

    assert outcome.status == Status.MERGED
    written = json.loads(target.read_text())
    assert written["model"] == "x"
    assert not jsonc.exists()


def test_jsonc_parse_failure_leaves_jsonc_intact(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode.json"
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({"model": "x"}))
    target_dir = tmp_path / "config" / "opencode"
    target_dir.mkdir(parents=True)
    jsonc = target_dir / "opencode.jsonc"
    jsonc.write_text("{ not valid json even after stripping }")
    target = target_dir / "opencode.json"

    with pytest.raises(ValueError):
        merged_for(target, base)

    assert jsonc.exists()


def test_opencode_config_carries_codegraph_entry(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode.json"
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({
        "mcp": {"servers": {"codegraph": {"type": "local", "command": ["codegraph", "serve", "--mcp"], "disabled": False, "codemode": False}}}
    }))
    target = tmp_path / "config" / "opencode" / "opencode.json"

    outcome = apply_merged(merged_for(target, base), Mode.APPLY)

    assert outcome.status == Status.MERGED
    entry = json.loads(target.read_text())["mcp"]["servers"]["codegraph"]
    assert entry == {"type": "local", "command": ["codegraph", "serve", "--mcp"], "disabled": False, "codemode": False}
