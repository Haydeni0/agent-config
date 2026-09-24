import json
import pathlib

import pytest

from settings_sync.config import sync_config
from settings_sync.sync import Status


def test_creates_config_from_base(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode.json"
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({"model": "anthropic/claude-sonnet-4-5"}))
    target = tmp_path / "config" / "opencode" / "opencode.json"

    outcome = sync_config(target, base)

    assert outcome.status == Status.CREATED
    written = json.loads(target.read_text())
    assert written["model"] == "anthropic/claude-sonnet-4-5"
    assert written["$schema"] == "https://opencode.ai/config.json"


def test_creates_with_empty_base_when_missing(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode.json"
    target = tmp_path / "config" / "opencode" / "opencode.json"

    outcome = sync_config(target, base)

    assert outcome.status == Status.CREATED
    written = json.loads(target.read_text())
    assert written == {"$schema": "https://opencode.ai/config.json"}


def test_unchanged_when_identical(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode.json"
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({"model": "x"}))
    target = tmp_path / "config" / "opencode" / "opencode.json"
    sync_config(target, base)

    outcome = sync_config(target, base)

    assert outcome.status == Status.UNCHANGED


def test_updates_declared_keys_without_force(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode.json"
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({"model": "new"}))
    target = tmp_path / "config" / "opencode" / "opencode.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"model": "hand-edited"}))

    outcome = sync_config(target, base)

    assert outcome.status == Status.REPLACED
    assert json.loads(target.read_text())["model"] == "new"


def test_force_overwrites_diverging_target(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode.json"
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({"model": "new"}))
    target = tmp_path / "config" / "opencode" / "opencode.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"model": "hand-edited"}))

    outcome = sync_config(target, base, force=True)

    assert outcome.status == Status.REPLACED
    assert json.loads(target.read_text())["model"] == "new"


def test_dry_run_does_not_write(tmp_path: pathlib.Path):
    base = tmp_path / "claude" / "opencode.json"
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({"model": "x"}))
    target = tmp_path / "config" / "opencode" / "opencode.json"

    outcome = sync_config(target, base, dry_run=True)

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

    outcome = sync_config(target, base)

    assert outcome.status == Status.CREATED
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

    outcome = sync_config(target, base)

    assert outcome.status == Status.FAILED
    assert jsonc.exists()
