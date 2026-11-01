"""Sync shared source config into ~/.config/goose (the goose harness)."""

from pathlib import Path

from settings_sync.actions import Outcome, Status
from settings_sync.ownership import prune_generated, sync_generated_json

from settings_sync.merging import sync_yaml_defaults
from settings_sync.sync import sync_dir_files


def sync_goose_config(target: Path, source: Path, force: bool = False, dry_run: bool = False) -> Outcome:
    """Merge declared Goose YAML defaults while preserving native local keys."""
    if not source.is_file():
        return Outcome(target, Status.NO_SOURCE, f"config source not found: {source}")
    content = source.read_text()
    return sync_yaml_defaults(target, content, dry_run=dry_run)


def sync_goose_providers(target_dir: Path, source_dir: Path, force: bool = False, dry_run: bool = False) -> list[Outcome]:
    """Sync ~/.claude/goose/custom_providers/*.json into ~/.config/goose/custom_providers/."""
    if not source_dir.is_dir():
        return [Outcome(target_dir, Status.NO_SOURCE, f"source dir not found: {source_dir}")]
    outcomes = sync_dir_files(
        target_dir, source_dir, pattern="*.json", force=force, dry_run=dry_run, sync_fn=sync_generated_json
    )
    expected = {p.name for p in source_dir.glob("*.json") if p.is_file()}
    outcomes.extend(prune_generated(target_dir, expected, dry_run))
    return outcomes
