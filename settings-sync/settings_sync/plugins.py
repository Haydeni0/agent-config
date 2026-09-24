"""Resolve the highest-cached superpowers version and symlink its opencode plugin."""

import re
from pathlib import Path

from settings_sync.sync import Outcome, Status
from settings_sync.ownership import sync_generated_symlink

_SUPERPOWERS_ROOT = Path("claude-plugins-official") / "superpowers"
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _parse_semver(name: str) -> tuple[int, ...]:
    return tuple(int(p) for p in name.split("."))


def resolve_superpowers_js(cache_root: Path) -> Path | None:
    superpowers_dir = cache_root / _SUPERPOWERS_ROOT
    if not superpowers_dir.is_dir():
        return None
    versions = [d.name for d in superpowers_dir.iterdir() if d.is_dir() and _VERSION_RE.match(d.name)]
    if not versions:
        return None
    highest = max(versions, key=_parse_semver)
    js = superpowers_dir / highest / ".opencode" / "plugins" / "superpowers.js"
    return js if js.is_file() else None


def sync_superpowers(target: Path, cache_root: Path, force: bool = False, dry_run: bool = False) -> Outcome:
    source = resolve_superpowers_js(cache_root)
    if source is None:
        return Outcome(target, Status.NO_SOURCE, "superpowers not found in cache")
    return sync_generated_symlink(target, source, force=force, dry_run=dry_run)


def sync_plugins(target: Path, source: Path, cache: Path, force: bool = False, dry_run: bool = False) -> list[Outcome]:
    """Install shared plugin links alongside native external plugins."""
    from settings_sync.ownership import prune_generated
    if not source.is_dir():
        return [Outcome(source, Status.FAILED, "required plugin source directory missing")]
    expected = {"superpowers.js"}
    outcomes: list[Outcome] = []
    for plugin in sorted(source.glob("*.js")):
        expected.add(plugin.name)
        outcomes.append(sync_generated_symlink(target / plugin.name, plugin, force, dry_run))
    outcomes.append(sync_superpowers(target / "superpowers.js", cache, force, dry_run))
    outcomes.extend(prune_generated(target, expected, dry_run))
    return outcomes
