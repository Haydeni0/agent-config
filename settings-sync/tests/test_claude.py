import json
from pathlib import Path

from typer.testing import CliRunner

from settings_sync.cli import agent_config_app


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
