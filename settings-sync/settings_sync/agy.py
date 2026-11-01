"""Deploy shared AGY (Antigravity) settings and resources."""

from pathlib import Path

from settings_sync.actions import Outcome, Status
from settings_sync.merging import sync_json_defaults
from settings_sync.ownership import prune_generated, sync_generated_symlink


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


def sync_agy_skills(
    target_dir: Path,
    source_dir: Path,
    force: bool = False,
    dry_run: bool = False,
) -> list[Outcome]:
    """Symlink each skill in source_dir into target_dir and remove orphans."""
    if not source_dir.is_dir():
        return [Outcome(target_dir, Status.NO_SOURCE, f"source dir not found: {source_dir}")]
    outcomes: list[Outcome] = []
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)
    source_names: set[str] = set()
    for source_sub in sorted(source_dir.iterdir(), key=lambda p: p.name):
        if not source_sub.is_dir():
            continue
        source_names.add(source_sub.name)
        outcomes.append(sync_generated_symlink(target_dir / source_sub.name, source_sub, force=force, dry_run=dry_run))
    outcomes.extend(prune_generated(target_dir, source_names, dry_run))
    return outcomes

