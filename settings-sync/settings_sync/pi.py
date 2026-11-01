"""Sync shared source config into ~/.pi/agent (the pi harness)."""

from pathlib import Path

from settings_sync.ownership import sync_generated_json

from settings_sync.merging import sync_json_defaults
from settings_sync.actions import Outcome, Status


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


def sync_pi_keybindings(target: Path, source: Path, dry_run: bool = False, *, force: bool = False) -> Outcome:
    """Install optional generated keybindings with local-edit protection."""
    if not source.is_file():
        return Outcome(target, Status.NO_SOURCE, f"keybindings source not found: {source}")
    content = source.read_text()
    return sync_generated_json(target, content, force=force, dry_run=dry_run)
