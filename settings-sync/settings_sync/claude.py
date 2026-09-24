"""Deploy shared Claude configuration while retaining native runtime state."""

import json
import re
import shlex
from pathlib import Path

from settings_sync.merging import sync_json_defaults
from settings_sync.ownership import prune_generated, sync_generated_symlink
from settings_sync.paths import Paths, config_home
from settings_sync.sync import Outcome, Status


def claude_home(paths: Paths) -> Path:
    return paths.claude_home or Path.home() / ".claude"



def runtime_command(command: str, home: Path) -> str:
    pattern = r'"\$HOME/\.claude([^"]*)"|~/\.claude([^\s;"\']*)'
    return re.sub(pattern, lambda match: shlex.quote(str(home) + (match[1] or match[2] or "")), command)


def sync_claude_config(paths: Paths, dry_run: bool) -> Outcome:
    target = claude_home(paths) / "settings.json"
    try:
        defaults = json.loads((paths.source_dir / "harnesses/claude/settings.json").read_text())
        if not isinstance(defaults, dict):
            raise ValueError("Claude settings must be a JSON object")
        for groups in defaults.get("hooks", {}).values():
            for group in groups:
                for hook in group.get("hooks", []):
                    if hook.get("type") == "command":
                        hook["command"] = runtime_command(hook["command"], claude_home(paths))
        status_line = defaults.get("statusLine", {})
        if status_line.get("type") == "command":
            status_line["command"] = runtime_command(status_line["command"], claude_home(paths))
        overlay_path = config_home() / "agent-config/overlays/claude.json"
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
        return sync_json_defaults(target, json.dumps(defaults), dry_run)
    except (OSError, ValueError) as exc:
        return Outcome(target, Status.FAILED, f"could not render Claude settings: {exc}")


def sync_claude_entries(paths: Paths, categories: tuple[str, ...], force: bool, dry_run: bool) -> list[Outcome]:
    home = claude_home(paths)
    outcomes: list[Outcome] = []
    for category in categories:
        source = paths.source_dir / category
        target = home / category
        if not source.is_dir():
            outcomes.append(Outcome(source, Status.FAILED, f"required {category} source directory missing"))
            continue
        names: set[str] = set()
        for entry in sorted(source.iterdir()):
            if entry.name.startswith("."):
                continue
            names.add(entry.name)
            outcomes.append(sync_generated_symlink(target / entry.name, entry, force, dry_run))
        outcomes.extend(prune_generated(target, names, dry_run))
    return outcomes


def sync_shared_skills(paths: Paths, dry_run: bool) -> list[Outcome]:
    outcomes = sync_claude_entries(paths, ("skills",), False, dry_run)
    outcomes.append(sync_generated_symlink(Path.home() / ".agents/skills", claude_home(paths) / "skills", dry_run=dry_run))
    return outcomes


def sync_claude_links(paths: Paths, force: bool, dry_run: bool) -> list[Outcome]:
    home = claude_home(paths)
    outcomes = sync_claude_entries(paths, ("skills", "commands", "agents"), force, dry_run)
    for alias, source in (
        ("custom", "custom"), ("hooks", "hooks"),
        ("statusline-command.sh", "harnesses/claude/statusline-command.sh"),
        ("pi", "harnesses/pi"), ("opencode", "harnesses/opencode"),
        ("settings-sync", "settings-sync"), ("opencode-resume", "opencode-resume"),
        ("codex", "harnesses/codex"), ("goose", "harnesses/goose"),
        ("gemini", "harnesses/gemini"), ("no-mistakes", "harnesses/no-mistakes"),
        ("README.md", "README.md"), ("sync.sh", "sync.sh"), ("scripts", "scripts"),
    ):
        entry = paths.source_dir / source
        if entry.exists():
            outcomes.append(sync_generated_symlink(home / alias, entry, force, dry_run))
    return outcomes
