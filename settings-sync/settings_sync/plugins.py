"""Resolve the highest-cached superpowers version and symlink its opencode plugin."""

import re
from pathlib import Path

from settings_sync.actions import Action, Prune, Report, Status, Symlink

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


def plan_plugins(target: Path, source: Path, cache: Path) -> list[Action]:
    """Install shared plugin links alongside native external plugins."""
    if not source.is_dir():
        return [Report(source, Status.FAILED, "required plugin source directory missing")]
    expected = {"superpowers.js"}
    actions: list[Action] = []
    for plugin in sorted(source.glob("*.js")):
        expected.add(plugin.name)
        actions.append(Symlink(target / plugin.name, plugin))
    superpowers = resolve_superpowers_js(cache)
    if superpowers is None:
        actions.append(Report(target / "superpowers.js", Status.NO_SOURCE, "superpowers not found in cache"))
    else:
        actions.append(Symlink(target / "superpowers.js", superpowers))
    actions.append(Prune(target, frozenset(expected)))
    return actions
