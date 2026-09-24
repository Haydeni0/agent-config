"""Sync shared source config into ~/.codex (the codex harness)."""

from pathlib import Path

from settings_sync.ownership import sync_generated_file

import tomlkit
from tomlkit.exceptions import ParseError

from settings_sync.agents_md import build_agents_md
from settings_sync.merging import merge_defaults, install_merged
from settings_sync.sync import Outcome, Status


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
