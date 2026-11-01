import os
import pathlib

import pytest

from settings_sync.plugins import resolve_superpowers_js, sync_superpowers
from settings_sync.actions import Status


def _make_version(cache_root: pathlib.Path, version: str) -> pathlib.Path:
    js = cache_root / "claude-plugins-official" / "superpowers" / version / ".opencode" / "plugins" / "superpowers.js"
    js.parent.mkdir(parents=True)
    js.write_text(f"// {version}")
    return js


def test_resolve_returns_highest_version(tmp_path: pathlib.Path):
    cache = tmp_path / "plugins" / "cache"
    _make_version(cache, "6.0.3")
    highest = _make_version(cache, "6.1.1")
    _make_version(cache, "6.1.0")
    assert resolve_superpowers_js(cache) == highest


def test_resolve_returns_none_when_not_cached(tmp_path: pathlib.Path):
    cache = tmp_path / "plugins" / "cache"
    cache.mkdir(parents=True)
    assert resolve_superpowers_js(cache) is None


def test_sync_creates_symlink_to_resolved_js(tmp_path: pathlib.Path):
    cache = tmp_path / "plugins" / "cache"
    _make_version(cache, "6.1.1")
    plugins_dir = tmp_path / "config" / "opencode" / "plugins"
    plugins_dir.mkdir(parents=True)
    target = plugins_dir / "superpowers.js"

    outcome = sync_superpowers(target, cache)

    assert outcome.status == Status.CREATED
    assert target.is_symlink()
    assert os.readlink(target).endswith("superpowers.js")
    assert target.read_text() == "// 6.1.1"


def test_sync_skips_when_superpowers_not_cached(tmp_path: pathlib.Path):
    cache = tmp_path / "plugins" / "cache"
    cache.mkdir(parents=True)
    plugins_dir = tmp_path / "config" / "opencode" / "plugins"
    plugins_dir.mkdir(parents=True)
    target = plugins_dir / "superpowers.js"

    outcome = sync_superpowers(target, cache)

    assert outcome.status == Status.NO_SOURCE
    assert not target.exists()
