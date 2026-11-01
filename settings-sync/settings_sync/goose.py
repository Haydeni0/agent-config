"""Sync shared source config into ~/.config/goose (the goose harness)."""

from pathlib import Path

from settings_sync.actions import Action, File, MergedConfig, Prune, Report, Status
from settings_sync.merging import YamlCodec
from settings_sync.paths import Paths


def plan_goose_config(paths: Paths) -> list[Action]:
    source = paths.source_dir / "harnesses/goose/config.yaml"
    return [MergedConfig(path=paths.target("goose") / "config.yaml", codec=YamlCodec(), keys=YamlCodec().loads(source.read_text()))]


def plan_goose_providers(paths: Paths) -> list[Action]:
    source_dir = paths.source_dir / "harnesses/goose/custom_providers"
    target_dir = paths.target("goose") / "custom_providers"
    if not source_dir.is_dir():
        return [Report(target_dir, Status.NO_SOURCE, f"source dir not found: {source_dir}")]
    actions = [File(target_dir / provider.name, provider.read_text())
               for provider in sorted(source_dir.glob("*.json"), key=lambda p: p.name) if provider.is_file()]
    actions.append(Prune(target_dir, frozenset(provider.name for provider in source_dir.glob("*.json") if provider.is_file())))
    return actions
