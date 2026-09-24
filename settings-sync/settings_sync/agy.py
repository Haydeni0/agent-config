"""Deploy shared AGY (Antigravity) settings and resources."""

from pathlib import Path

from settings_sync.agents_md import sync_agents_md
from settings_sync.merging import sync_json_defaults
from settings_sync.sync import Outcome, Status, sync_dir_symlinks


def sync_agy_settings(
    target: Path,
    source: Path,
    force: bool = False,
    dry_run: bool = False,
) -> Outcome:
    """Merge shared Gemini settings into the native settings file."""
    if not source.is_file():
        return Outcome(target, Status.NO_SOURCE, f"settings source not found: {source}")
    return sync_json_defaults(target, source.read_text(), dry_run=dry_run)


def sync_agy_agents_md(
    target: Path,
    claude_md: Path,
    force: bool = False,
    dry_run: bool = False,
    *, source_root: Path | None = None,
) -> Outcome:
    """Sync CLAUDE.md -> AGENTS.md (rewriting @skills/<n> refs)."""
    return sync_agents_md(target, claude_md, force=force, dry_run=dry_run, source_root=source_root, harness="agy")


def sync_agy_skills(
    target_dir: Path,
    source_dir: Path,
    force: bool = False,
    dry_run: bool = False,
) -> list[Outcome]:
    """Symlink each skill in source_dir into target_dir and remove orphans."""
    return sync_dir_symlinks(target_dir, source_dir, force=force, dry_run=dry_run)
