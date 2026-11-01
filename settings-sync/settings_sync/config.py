"""Read the base opencode config from ~/.claude and write the generated opencode.json."""

import json
from collections.abc import Mapping
from pathlib import Path

from settings_sync.actions import Action, MergedConfig
from settings_sync.merging import JsonCodec, strip_jsonc
from settings_sync.paths import Paths

OPENCODE_SCHEMA = "https://opencode.ai/config.json"
TUI_SCHEMA = "https://opencode.ai/tui.json"

def build_config(base_path: Path) -> dict:
    if base_path.is_file():
        config = json.loads(base_path.read_text())
    else:
        config = {}
    if not isinstance(config, dict):
        raise ValueError("configuration must be a JSON object")
    config.setdefault("$schema", OPENCODE_SCHEMA)
    return config


def build_tui(base_path: Path) -> dict:
    if base_path.is_file():
        config = json.loads(base_path.read_text())
    else:
        config = {}
    config.setdefault("$schema", TUI_SCHEMA)
    return config


def plan_opencode_config(paths: Paths) -> list[Action]:
    target = paths.opencode_dir / "opencode.json"
    legacy = target.with_suffix(".jsonc")
    if legacy.is_symlink() or legacy.exists() and not legacy.is_file():
        raise ValueError(f"legacy entry is not a regular file; preserve and resolve {legacy}")
    config = build_config(paths.source_dir / "harnesses/opencode/opencode.json")
    migrate: Mapping[str, object] | None = None
    if legacy.is_file():
        migrate = json.loads(strip_jsonc(legacy.read_text()))
        if not isinstance(migrate, dict):
            raise ValueError("legacy JSON must be an object")
    return [MergedConfig(path=target, codec=JsonCodec(), keys=config,
                         migrate=migrate, remove_after=legacy if migrate is not None else None)]


def plan_opencode_tui(paths: Paths) -> list[Action]:
    return [MergedConfig(path=paths.opencode_dir / "tui.json", codec=JsonCodec(),
                         keys=build_tui(paths.source_dir / "harnesses/opencode/tui.json"))]
