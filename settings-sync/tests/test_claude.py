import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from settings_sync.actions import Mode, Outcome, Status
from settings_sync.claude import plan_claude_config
from settings_sync.cli import agent_config_app
from settings_sync.executor import execute
from settings_sync.ownership import OwnershipStore
from settings_sync.paths import resolve_paths


def apply_claude_config(paths, mode: Mode) -> list[Outcome]:
    store = OwnershipStore()
    store.load(mode)
    return execute(plan_claude_config(paths), mode, store)


def test_external_source_claude_preserves_local_entries(tmp_path: Path, isolated_home: Path):
    source = tmp_path / "source repo"
    (source / "rules").mkdir(parents=True)
    (source / "rules/global.md").write_text("# Complete rules\nSee @skills/example.\n")
    (source / "harnesses/claude").mkdir(parents=True)
    (source / "harnesses/claude/settings.json").write_text('{"permissions":{"allow":["shared"]}}')
    (source / "harnesses/claude/statusline-command.sh").write_text("echo status\n")
    for directory in ("skills/example", "commands", "agents", "custom", "hooks"):
        (source / directory).mkdir(parents=True)
    skill = source / "skills/example/SKILL.md"
    skill.write_text("Shared skill")
    local = isolated_home / ".claude/skills/synced/local/SKILL.md"
    local.parent.mkdir(parents=True)
    local.write_text("Keep local skill")
    target = isolated_home / ".claude/settings.json"
    target.write_text('{"native":"keep"}')
    overlay = isolated_home / ".config/agent-config/overlays/claude.json"
    overlay.parent.mkdir(parents=True)
    overlay.write_text('{"permissions":{"allow":["machine-only","shared"]}}')
    runner = CliRunner()
    args = ["--source", str(source), "sync", "claude"]
    result = runner.invoke(agent_config_app, args)
    assert result.exit_code == 0, result.output
    config = json.loads(target.read_text())
    assert config["permissions"]["allow"] == ["shared", "machine-only"]
    assert config["native"] == "keep"
    assert local.read_text() == "Keep local skill"
    instructions = (isolated_home / ".claude/CLAUDE.md").read_text()
    assert str(source) in instructions
    assert "# Complete rules\nSee @skills/example." in instructions
    alias = isolated_home / ".claude/skills/example/SKILL.md"
    alias.write_text("Edited through runtime alias")
    assert skill.read_text() == "Edited through runtime alias"
    (source / "harnesses/claude/settings.json").write_text('{"permissions":{"allow":["shared","new-shared"]}}')
    assert runner.invoke(agent_config_app, args).exit_code == 0
    assert json.loads(target.read_text())["permissions"]["allow"] == ["shared","new-shared","machine-only"]


def test_custom_claude_home_runs_its_source_hook(source_home: Path, isolated_home: Path):
    import subprocess
    script = source_home / "custom/hook.sh"
    script.write_text("echo selected-hook\n")
    settings = source_home / "harnesses/claude/settings.json"
    settings.write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": 'bash "$HOME/.claude/custom/hook.sh"'}]}]}, "statusLine": {"type": "command", "command": "bash ~/.claude/custom/hook.sh"}}))
    custom = isolated_home / "custom claude home"
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "--claude-home", str(custom), "sync", "claude"])
    assert result.exit_code == 0, result.output
    config = json.loads((custom / "settings.json").read_text())
    for command in (config["hooks"]["SessionStart"][0]["hooks"][0]["command"], config["statusLine"]["command"]):
        executed = subprocess.run(["bash", "-c", command], capture_output=True, text=True)
        assert executed.returncode == 0, executed.stderr
        assert executed.stdout == "selected-hook\n"


def test_claude_permissions_include_codegraph(tmp_path: Path, isolated_home: Path):
    from settings_sync.paths import resolve_paths

    source = tmp_path / "source"
    (source / "harnesses/claude").mkdir(parents=True)
    (source / "harnesses/claude/settings.json").write_text(json.dumps({"permissions": {"allow": ["mcp__codegraph__*"]}}))
    target = isolated_home / ".claude/settings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"permissions": {"allow": ["Bash(git status*)"]}}))
    paths = resolve_paths(claude_dir=source, claude_home=target.parent)
    apply_claude_config(paths, Mode.APPLY)
    allow = json.loads(target.read_text())["permissions"]["allow"]
    # Declared arrays replace (REQ-SYNC-04): the template allow list wins.
    assert "mcp__codegraph__*" in allow
    assert "Bash(git status*)" not in allow


REPO = Path(__file__).resolve().parents[2]
FOREIGN_GROUP = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo local-hook"}]}


def synced_claude_settings(source_home: Path, isolated_home: Path) -> tuple[Outcome, Path]:
    """Sync the real Claude template into an isolated home that already carries a foreign hook and a local key."""
    shutil.copyfile(REPO / "harnesses/claude/settings.json", source_home / "harnesses/claude/settings.json")
    target = isolated_home / ".claude/settings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"hooks": {"PreToolUse": [FOREIGN_GROUP]}, "localKey": "keep"}))
    paths = resolve_paths(claude_dir=source_home, claude_home=target.parent)
    return apply_claude_config(paths, Mode.APPLY)[0], target


def installed_guard_command(target: Path) -> str:
    groups = json.loads(target.read_text())["hooks"]["PreToolUse"]
    commands = [hook["command"] for group in groups if group.get("matcher") == "Bash" for hook in group["hooks"]]
    guards = [command for command in commands if "hooks/command.mjs" in command]
    assert len(guards) == 1, commands
    return guards[0]


def run_hook(command: str, payload: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", command], input=json.dumps(payload), capture_output=True, text=True)


def test_synced_claude_guard_denies_and_preserves_local_state(source_home: Path, isolated_home: Path):
    outcome, target = synced_claude_settings(source_home, isolated_home)
    assert outcome.status != Status.FAILED, outcome.detail
    config = json.loads(target.read_text())
    assert config["localKey"] == "keep"
    assert FOREIGN_GROUP in config["hooks"]["PreToolUse"]
    result = run_hook(
        installed_guard_command(target),
        {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "sudo true"}},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_synced_claude_guard_fails_closed_on_malformed_payload(source_home: Path, isolated_home: Path):
    _, target = synced_claude_settings(source_home, isolated_home)
    result = run_hook(installed_guard_command(target), {"tool_input": {"command": "sudo true"}})
    assert (result.returncode, result.stdout) == (2, "")


def test_synced_claude_guard_denies_cursor_payload(source_home: Path, isolated_home: Path):
    _, target = synced_claude_settings(source_home, isolated_home)
    result = run_hook(
        installed_guard_command(target),
        {"hook_event_name": "preToolUse", "tool_name": "Shell", "tool_input": {"command": "sudo true"}},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_claude_guard_sync_without_node_fails_untouched(
    source_home: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
):
    empty_bin = isolated_home / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    target = isolated_home / ".claude/settings.json"
    target.parent.mkdir(parents=True)
    before = json.dumps({"hooks": {"PreToolUse": [FOREIGN_GROUP]}, "localKey": "keep"})
    target.write_text(before)
    shutil.copyfile(REPO / "harnesses/claude/settings.json", source_home / "harnesses/claude/settings.json")
    paths = resolve_paths(claude_dir=source_home, claude_home=target.parent)
    with pytest.raises(ValueError, match="Node.js"):
        plan_claude_config(paths)
    assert target.read_text() == before


def test_synced_claude_settings_have_no_inline_gh_api_hook(source_home: Path, isolated_home: Path):
    _, target = synced_claude_settings(source_home, isolated_home)
    groups = json.loads(target.read_text())["hooks"]["PreToolUse"]
    commands = [hook["command"] for group in groups for hook in group["hooks"]]
    assert not [command for command in commands if "gh api" in command]
