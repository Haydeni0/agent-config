"""Sync shared source config into ~/.codex (the codex harness)."""

import stat
from pathlib import Path

from settings_sync.ownership import sync_generated_file

import tomlkit
from tomlkit.exceptions import ParseError

from settings_sync.agents_md import build_agents_md
from settings_sync.merging import merge_defaults, install_merged
from settings_sync.sync import Outcome, Status

CODEX_SQLITE_HOME_MODE = 0o700


def sync_codex_sqlite_home(template: Path, dry_run: bool = False) -> Outcome:
    """Provision the configured SQLite runtime directory on the local machine."""
    if not template.is_file():
        return Outcome(template, Status.NO_SOURCE, f"template not found: {template}")
    try:
        defaults = tomlkit.parse(template.read_text())
    except ParseError as exc:
        return Outcome(template, Status.FAILED, f"invalid Codex template: {exc}")

    configured = defaults.get("sqlite_home")
    if configured is None:
        return Outcome(template, Status.UNCHANGED, "sqlite_home not configured")
    if not isinstance(configured, str):
        return Outcome(template, Status.FAILED, "sqlite_home must be a string path")

    sqlite_home = Path(configured)
    if not sqlite_home.is_absolute():
        return Outcome(sqlite_home, Status.FAILED, "sqlite_home must be an absolute path")
    if sqlite_home.is_symlink():
        return Outcome(sqlite_home, Status.FAILED, "sqlite_home must not be a symlink")

    try:
        if not sqlite_home.exists():
            if dry_run:
                return Outcome(sqlite_home, Status.WOULD_CREATE, "private SQLite runtime directory")
            sqlite_home.mkdir(parents=True, mode=CODEX_SQLITE_HOME_MODE)
            sqlite_home.chmod(CODEX_SQLITE_HOME_MODE)
            return Outcome(sqlite_home, Status.CREATED, "private SQLite runtime directory")
        if not sqlite_home.is_dir():
            return Outcome(sqlite_home, Status.FAILED, "sqlite_home exists but is not a directory")

        mode = stat.S_IMODE(sqlite_home.stat().st_mode)
        if mode == CODEX_SQLITE_HOME_MODE:
            return Outcome(sqlite_home, Status.UNCHANGED, "private SQLite runtime directory")
        if dry_run:
            return Outcome(sqlite_home, Status.WOULD_REPLACE, f"directory mode {mode:o}; expected 700")
        sqlite_home.chmod(CODEX_SQLITE_HOME_MODE)
        return Outcome(sqlite_home, Status.REPLACED, f"directory mode {mode:o} -> 700")
    except OSError as exc:
        return Outcome(sqlite_home, Status.FAILED, f"could not provision SQLite runtime directory: {exc}")


def sync_codex_config(target: Path, template: Path, dry_run: bool = False) -> Outcome:
    """Apply template keys while preserving local keys and TOML formatting.

    Tables merge recursively; scalar and array values replace managed keys.
    Keys omitted from the template retain their installed values.
    """
    if not template.is_file():
        return Outcome(target, Status.NO_SOURCE, f"template not found: {template}")
    try:
        defaults = tomlkit.parse(template.read_text())
    except ParseError as exc:
        return Outcome(target, Status.FAILED, f"invalid Codex template: {exc}")

    if target.is_symlink():
        return Outcome(target, Status.FAILED, "expected regular configuration file; destination is a symlink")
    try:
        content = target.read_text()
    except FileNotFoundError:
        content = None
    try:
        config = tomlkit.parse(content or "")
    except ParseError as exc:
        return Outcome(target, Status.FAILED, f"invalid installed Codex config: {exc}")

    merge_defaults(config, defaults)
    return install_merged(target, tomlkit.dumps(config), content, dry_run)


def sync_codex_agents_md(target: Path, claude_md: Path, force: bool = False, dry_run: bool = False, *, source_root: Path | None = None) -> Outcome:
    """Inline CLAUDE.md (@skills/x rewritten) into ~/.codex/AGENTS.md.

    Codex reads global instructions from $CODEX_HOME/AGENTS.md. Same transform
    as opencode's AGENTS.md (build_agents_md with rules_path=None). Updates unchanged managed output; locally edited output requires force and a backup.
    """
    if not claude_md.is_file():
        return Outcome(target, Status.NO_SOURCE, f"CLAUDE.md not found: {claude_md}")
    content = build_agents_md(claude_md, rules_path=None, source_root=source_root, harness="codex")
    return sync_generated_file(target, content, force=force, dry_run=dry_run)
