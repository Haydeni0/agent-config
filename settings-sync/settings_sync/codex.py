"""Sync shared source config into ~/.codex (the codex harness)."""

from pathlib import Path

import tomlkit

from settings_sync.actions import Action, Directory, MergedConfig
from settings_sync.merging import TomlCodec
from settings_sync.paths import Paths

CODEX_SQLITE_HOME_MODE = 0o700


def plan_codex_config(paths: Paths) -> list[Action]:
    template = paths.source_dir / "harnesses/codex/config.toml"
    defaults = tomlkit.parse(template.read_text())
    actions: list[Action] = []
    configured = defaults.get("sqlite_home")
    if configured is not None:
        if not isinstance(configured, str):
            raise ValueError("sqlite_home must be a string path")
        sqlite_home = Path(configured)
        if not sqlite_home.is_absolute():
            raise ValueError("sqlite_home must be an absolute path")
        if sqlite_home.is_symlink():
            raise ValueError("sqlite_home must not be a symlink")
        actions.append(Directory(sqlite_home, CODEX_SQLITE_HOME_MODE))
    actions.append(MergedConfig(path=paths.target("codex") / "config.toml", codec=TomlCodec(), keys=tomlkit.parse(template.read_text())))
    return actions
