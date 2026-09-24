from pathlib import Path

import pytest
from typer.testing import CliRunner

from settings_sync.cli import agent_config_app


@pytest.mark.parametrize("harness,target", [
    ("claude", ".claude/CLAUDE.md"), ("codex", ".codex/AGENTS.md"),
    ("opencode", ".config/opencode/AGENTS.md"), ("pi", ".pi/agent/CLAUDE.md"),
    ("goose", ".config/goose/.goosehints"), ("agy", ".gemini/config/AGENTS.md"),
])
def test_routing_preserves_complete_rule_body(source_home: Path, isolated_home: Path, harness: str, target: str):
    body = "# Rules\nFirst section.\nSee @skills/uv.\n## Last section\nKeep every paragraph.\n"
    (source_home / "rules/global.md").write_text(body)
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", harness])
    assert result.exit_code == 0, result.output
    installed = (isolated_home / target).read_text()
    assert str(source_home) in installed
    assert f"agent-config sync {harness}" in installed
    assert "rules/global.md" in installed
    expected = body if harness == "claude" else body.replace("@skills/uv", "the `uv` skill")
    assert installed.endswith(expected)


def test_runtime_superpowers_cache_used(source_home: Path, isolated_home: Path):
    plugin = isolated_home / ".claude/plugins/cache/claude-plugins-official/superpowers/1.0.0/.opencode/plugins/superpowers.js"
    plugin.parent.mkdir(parents=True)
    plugin.write_text("export default {}")
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "opencode", "plugins"])
    assert result.exit_code == 0, result.output
    assert (isolated_home / ".config/opencode/plugins/superpowers.js").resolve() == plugin


def test_pi_only_sync_installs_native_resources(source_home: Path, isolated_home: Path):
    (source_home / "skills/example").mkdir()
    (source_home / "skills/example/SKILL.md").write_text("Shared skill")
    (source_home / "commands/example.md").write_text("Shared command")
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "pi"])
    assert result.exit_code == 0, result.output
    assert (isolated_home / ".claude/skills/example/SKILL.md").read_text() == "Shared skill"
    assert (isolated_home / ".claude/commands/example.md").read_text() == "Shared command"


def test_opencode_installs_shared_plugins_preserving_external_ones(source_home: Path, isolated_home: Path):
    source = source_home / "harnesses/opencode/plugins"
    source.mkdir(exist_ok=True)
    (source / "guard.js").write_text("export default {}")
    target = isolated_home / ".config/opencode/plugins"
    target.mkdir(parents=True)
    (target / "external.js").write_text("Personal plugin")
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "opencode", "plugins"])
    assert result.exit_code == 0, result.output
    assert (target / "guard.js").resolve() == source / "guard.js"
    assert (target / "external.js").read_text() == "Personal plugin"


@pytest.mark.parametrize("harness", ["opencode", "goose"])
def test_standalone_harness_installs_shared_skill(source_home: Path, isolated_home: Path, harness: str):
    skill = source_home / "skills/example/SKILL.md"
    skill.parent.mkdir()
    skill.write_text("Shared skill")
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", harness])
    assert result.exit_code == 0, result.output
    assert (isolated_home / ".claude/skills/example/SKILL.md").read_text() == "Shared skill"


def test_pi_uses_selected_claude_runtime(source_home: Path, isolated_home: Path):
    import json
    runtime = isolated_home / "custom runtime"
    template = source_home / "harnesses/pi/settings.json"
    template.write_text(json.dumps({"skills": ["~/.claude/skills"], "prompts": ["~/.claude/commands"]}))
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "--claude-home", str(runtime), "sync", "pi"])
    assert result.exit_code == 0, result.output
    settings = json.loads((isolated_home / ".pi/agent/settings.json").read_text())
    assert settings["skills"] == [str(runtime / "skills")]
    assert settings["prompts"] == [str(runtime / "commands")]
