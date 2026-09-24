"""Sync ~/.claude config into ~/.codex (the codex harness)."""

from collections.abc import Mapping, MutableMapping
from pathlib import Path

import tomlkit
from tomlkit.exceptions import ParseError

from settings_sync.agents_md import build_agents_md
from settings_sync.sync import Outcome, Status, sync_text


def _merge_defaults(target: MutableMapping[str, object], source: Mapping[str, object]) -> None:
    for key, value in source.items():
        existing = target.get(key)
        if isinstance(existing, MutableMapping) and isinstance(value, Mapping):
            _merge_defaults(existing, value)
        elif existing != value:
            target[key] = value


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

    try:
        content = target.read_text()
    except FileNotFoundError:
        content = ""
    try:
        config = tomlkit.parse(content)
    except ParseError as exc:
        return Outcome(target, Status.FAILED, f"invalid installed Codex config: {exc}")

    _merge_defaults(config, defaults)
    return sync_text(target, tomlkit.dumps(config), force=True, dry_run=dry_run)


def sync_codex_agents_md(target: Path, claude_md: Path, force: bool = False, dry_run: bool = False) -> Outcome:
    """Inline CLAUDE.md (@skills/x rewritten) into ~/.codex/AGENTS.md.

    Codex reads global instructions from $CODEX_HOME/AGENTS.md. Same transform
    as opencode's AGENTS.md (build_agents_md with rules_path=None). Refuses to
    clobber a diverging file without --force, matching AGENTS.md handling.
    """
    if not claude_md.is_file():
        return Outcome(target, Status.NO_SOURCE, f"CLAUDE.md not found: {claude_md}")
    content = build_agents_md(claude_md, rules_path=None)
    return sync_text(target, content, force=force, dry_run=dry_run)
