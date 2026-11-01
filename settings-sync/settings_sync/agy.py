"""Deploy shared AGY (Antigravity) settings and resources."""

import json
from pathlib import Path

from settings_sync.actions import Action, MergedConfig, Prune, Symlink
from settings_sync.merging import JsonCodec
from settings_sync.paths import Paths



def plan_agy_settings(paths: Paths) -> list[Action]:
    source = paths.source_dir / "harnesses/gemini/settings.json"
    return [MergedConfig(path=(paths.agy_cli_dir or paths.target("agy")) / "settings.json",
                         codec=JsonCodec(), keys=json.loads(source.read_text()))]


def plan_agy_skills(paths: Paths) -> list[Action]:
    source_dir = paths.source_dir / "skills"
    target_dir = paths.target("agy") / "skills"
    skills = sorted((entry for entry in source_dir.iterdir() if entry.is_dir()), key=lambda p: p.name)
    actions = [Symlink(target_dir / skill.name, skill) for skill in skills]
    actions.append(Prune(target_dir, frozenset(skill.name for skill in skills)))
    return actions
