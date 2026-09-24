"""Sync shared source config into ~/.pi/agent (the pi harness)."""

from pathlib import Path

from settings_sync.ownership import sync_generated_file, sync_generated_json

from settings_sync.agents_md import build_agents_md
from settings_sync.merging import sync_json_defaults
from settings_sync.sync import Outcome, Status


def sync_pi_config(target: Path, template: Path, dry_run: bool = False, *, source_root: Path | None = None, runtime_home: Path | None = None) -> Outcome:
    """Apply declared defaults while retaining Pi local state."""
    if not template.is_file():
        return Outcome(target, Status.NO_SOURCE, f"template not found: {template}")
    content = template.read_text()
    if source_root is not None:
        import json
        content = content.replace("${AGENT_CONFIG_REPO}", json.dumps(str(source_root))[1:-1])
    if runtime_home is not None and runtime_home != Path.home() / ".claude":
        import json
        content = content.replace("~/.claude/", json.dumps(str(runtime_home))[1:-1] + "/")
    return sync_json_defaults(target, content, dry_run=dry_run)


def sync_pi_context(target: Path, claude_md: Path, force: bool = False, dry_run: bool = False, *, source_root: Path | None = None) -> Outcome:
    """Inline CLAUDE.md (@imports expanded, @skills/x rewritten) into <agent>/CLAUDE.md.

    pi can't expand @ imports, so we inline them here (same transform opencode's
    AGENTS.md uses, via build_agents_md with rules_path=None). Updates unchanged managed output; locally edited output requires force and a backup.
    """
    if not claude_md.is_file():
        return Outcome(target, Status.NO_SOURCE, f"CLAUDE.md not found: {claude_md}")
    content = build_agents_md(claude_md, rules_path=None, source_root=source_root, harness="pi")
    return sync_generated_file(target, content, force=force, dry_run=dry_run)


def sync_pi_keybindings(target: Path, source: Path, dry_run: bool = False, *, force: bool = False) -> Outcome:
    """Install optional generated keybindings with local-edit protection."""
    if not source.is_file():
        return Outcome(target, Status.NO_SOURCE, f"keybindings source not found: {source}")
    content = source.read_text()
    return sync_generated_json(target, content, force=force, dry_run=dry_run)
