"""Deploy shared Claude configuration while retaining native runtime state."""

import json
import re
import shlex
from pathlib import Path

from settings_sync.actions import Action, MergedConfig, Prune, Symlink
from settings_sync.hooks import expand_command_hooks, has_command_placeholder, hook_groups
from settings_sync.merging import JsonCodec
from settings_sync.paths import Paths


def runtime_command(command: str, home: Path) -> str:
    pattern = r'"\$HOME/\.claude([^"]*)"|~/\.claude([^\s;"\']*)'
    return re.sub(pattern, lambda match: shlex.quote(str(home) + (match[1] or match[2] or "")), command)


def plan_claude_config(paths: Paths) -> list[Action]:
    defaults = json.loads((paths.source_dir / "harnesses/claude/settings.json").read_text())
    if not isinstance(defaults, dict):
        raise ValueError("Claude settings must be a JSON object")
    hooks = hook_groups(defaults.get("hooks", {}))
    if has_command_placeholder(hooks):
        expand_command_hooks(paths.source_dir, "claude", hooks)
    for groups in hooks.values():
        for group in groups:
            for hook in group.get("hooks", []):
                if hook.get("type") == "command":
                    hook["command"] = runtime_command(hook["command"], paths.claude_home)
    status_line = defaults.get("statusLine", {})
    if status_line.get("type") == "command":
        status_line["command"] = runtime_command(status_line["command"], paths.claude_home)
    overlay_path = paths.overlay_dir / "claude.json"
    if overlay_path.exists():
        overlay = json.loads(overlay_path.read_text())
        if not isinstance(overlay, dict) or set(overlay) - {"permissions"}:
            raise ValueError("Claude overlay accepts only permissions.allow")
        permissions = overlay.get("permissions", {})
        if not isinstance(permissions, dict) or set(permissions) - {"allow"}:
            raise ValueError("Claude overlay accepts only permissions.allow")
        additions = permissions.get("allow", [])
        if not isinstance(additions, list) or not all(isinstance(item, str) for item in additions):
            raise ValueError("Claude overlay permissions.allow must be a list of strings")
        shared_permissions = defaults.setdefault("permissions", {})
        if not isinstance(shared_permissions, dict):
            raise ValueError("shared permissions must be an object")
        shared = shared_permissions.setdefault("allow", [])
        if not isinstance(shared, list) or not all(isinstance(item, str) for item in shared):
            raise ValueError("shared permissions.allow must be a list of strings")
        shared.extend(item for item in additions if item not in shared)
    return [MergedConfig(path=paths.claude_home / "settings.json", codec=JsonCodec(), keys=defaults, hook_key="hooks")]


def plan_claude_entries(paths: Paths, categories: tuple[str, ...]) -> list[Action]:
    actions: list[Action] = []
    for category in categories:
        source = paths.source_dir / category
        target = paths.claude_home / category
        names = frozenset(entry.name for entry in source.iterdir() if not entry.name.startswith("."))
        actions.extend(Symlink(target / name, source / name) for name in sorted(names))
        actions.append(Prune(target, names))
    return actions


def plan_shared_skills(paths: Paths) -> list[Action]:
    target = paths.shared_skills
    source = paths.source_dir / "skills"
    legacy = paths.claude_home / "skills"
    if target.is_symlink() and target.resolve() == legacy.resolve() and legacy.is_dir():
        local = sorted(
            entry.name for entry in legacy.iterdir()
            if not entry.name.startswith(".") and entry.name != "synced"
            and entry.resolve() != (source / entry.name).resolve()
        )
        if local:
            return [Symlink(target, source, detail=(
                f"legacy skills need reconciliation before changing discovery: {', '.join(local)}; "
                "move shared skills into the source checkout and sync claude links first"))]
    return [Symlink(target, source)]


_REPO_ALIASES = (
    ("custom", "custom"), ("hooks", "hooks"),
    ("statusline-command.sh", "harnesses/claude/statusline-command.sh"),
    ("settings-sync", "settings-sync"), ("opencode-resume", "opencode-resume"),
    ("README.md", "README.md"), ("sync.sh", "sync.sh"), ("scripts", "scripts"),
)


def plan_claude_links(paths: Paths) -> list[Action]:
    actions = plan_claude_entries(paths, ("skills", "commands", "agents"))
    actions.extend(
        Symlink(paths.claude_home / alias, paths.source_dir / source)
        for alias, source in _REPO_ALIASES
        if (paths.source_dir / source).exists()
    )
    return actions
