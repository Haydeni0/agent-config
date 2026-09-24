"""Sync shared source config into ~/.config/goose (the goose harness)."""

from pathlib import Path

from settings_sync.ownership import sync_generated_file, sync_generated_json

from settings_sync.agents_md import build_agents_md
from settings_sync.merging import sync_yaml_defaults
from settings_sync.sync import Outcome, Status, sync_dir_files


def sync_goose_hints(target: Path, claude_md: Path, force: bool = False, dry_run: bool = False, *, source_root: Path | None = None) -> Outcome:
    """Inline CLAUDE.md (@imports expanded, @skills/x rewritten) into .goosehints.

    goose supports @ imports natively, but we inline them for consistency with
    opencode (AGENTS.md) and pi (CLAUDE.md) - single self-contained file, no
    dependency on goose's @ resolution behaviour. Same transform via
    build_agents_md with rules_path=None. Refuses to clobber a diverging file
    without --force.
    """
    if not claude_md.is_file():
        return Outcome(target, Status.NO_SOURCE, f"CLAUDE.md not found: {claude_md}")
    content = build_agents_md(claude_md, rules_path=None, source_root=source_root, harness="goose")
    return sync_generated_file(target, content, force=force, dry_run=dry_run)


def sync_goose_config(target: Path, source: Path, force: bool = False, dry_run: bool = False) -> Outcome:
    """Merge declared Goose YAML defaults while preserving native local keys."""
    if not source.is_file():
        return Outcome(target, Status.NO_SOURCE, f"config source not found: {source}")
    content = source.read_text()
    return sync_yaml_defaults(target, content, dry_run=dry_run)


def sync_goose_providers(target_dir: Path, source_dir: Path, force: bool = False, dry_run: bool = False) -> list[Outcome]:
    """Sync ~/.claude/goose/custom_providers/*.json into ~/.config/goose/custom_providers/."""
    return sync_dir_files(target_dir, source_dir, pattern="*.json", force=force, dry_run=dry_run, sync_fn=sync_generated_json)
