"""Sync shared source config into ~/.pi/agent (the pi harness)."""

import json
from pathlib import Path

from settings_sync.actions import Action, File, MergedConfig, Report, Status
from settings_sync.merging import JsonCodec
from settings_sync.paths import Paths


def plan_pi_config(paths: Paths) -> list[Action]:
    template = paths.source_dir / "harnesses/pi/settings.json"
    content = template.read_text()
    content = content.replace("${AGENT_CONFIG_REPO}", json.dumps(str(paths.source_dir))[1:-1])
    if paths.claude_home is not None and paths.claude_home != paths.home / ".claude":
        content = content.replace("~/.claude/", json.dumps(str(paths.claude_home))[1:-1] + "/")
    return [MergedConfig(path=paths.target("pi") / "settings.json", codec=JsonCodec(), keys=json.loads(content))]


def plan_pi_keybindings(paths: Paths) -> list[Action]:
    source = paths.source_dir / "harnesses/pi/keybindings.json"
    target = paths.target("pi") / "keybindings.json"
    if not source.is_file():
        return [Report(target, Status.NO_SOURCE, f"keybindings source not found: {source}")]
    return [File(target, source.read_text())]
