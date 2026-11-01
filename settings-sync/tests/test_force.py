"""Force semantics: what --force must and must not override (REQ-SYNC-02, REQ-SYNC-12)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from settings_sync.cli import agent_config_app


def _synced_commands(source: Path, home: Path) -> tuple[Path, Path]:
    (source / "commands" / "managed.md").write_text("---\ndescription: managed\n---\nBody\n")
    args = ["--source", str(source)]
    result = CliRunner().invoke(agent_config_app, [*args, "sync", "opencode", "commands"])
    assert result.exit_code == 0, result.output
    return (home / ".config" / "opencode" / "commands"), args


def test_edited_managed_orphan_preserved_under_force(source_home: Path, isolated_home: Path) -> None:
    """S33: an edited managed orphan is warned and preserved, even under --force (REQ-SYNC-12)."""
    target, args = _synced_commands(source_home, isolated_home)
    (source_home / "commands" / "managed.md").unlink()
    (target / "managed.md").write_text("local edit\n")
    result = CliRunner().invoke(agent_config_app, [*args, "sync", "opencode", "commands", "--force"])
    assert result.exit_code == 1, result.output
    assert (target / "managed.md").read_text() == "local edit\n"
    assert "warned" in result.output


def _edited(path: Path, content: str) -> None:
    """Replace a managed file or link with edited local content - never write through a link."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


FILE_LINK_STEPS = [
    ("claude", "context", ".claude/CLAUDE.md"),
    ("claude", "links", ".claude/skills/uv"),
    ("opencode", "resources", ".claude/skills/uv"),
    ("opencode", "agents-md", ".config/opencode/AGENTS.md"),
    ("opencode", "agents", ".config/opencode/agents/reviewer.md"),
    ("opencode", "commands", ".config/opencode/commands/foo.md"),
    ("opencode", "plugins", ".config/opencode/plugins/shared.js"),
    ("pi", "resources", ".claude/skills/uv"),
    ("pi", "context", ".pi/agent/CLAUDE.md"),
    ("pi", "keybindings", ".pi/agent/keybindings.json"),
    ("goose", "resources", ".claude/skills/uv"),
    ("goose", "hints", ".config/goose/.goosehints"),
    ("goose", "providers", ".config/goose/custom_providers/glm.json"),
    ("goose", "hooks", ".agents/plugins/agent-config-goose/plugin.json"),
    ("agy", "agents-md", ".gemini/config/AGENTS.md"),
    ("agy", "skills", ".gemini/config/skills/uv"),
    ("codex", "agents-md", ".codex/AGENTS.md"),
    ("codex", "skills", ".agents/skills"),
    ("codegraph", "binary", ".local/bin/codegraph"),
]


def _seed(source_home: Path, harness: str, step: str) -> None:
    for directory in ("skills/uv", "commands", "agents", "harnesses/opencode/plugins", "harnesses/goose/custom_providers", "harnesses/pi"):
        (source_home / directory).mkdir(parents=True, exist_ok=True)
    (source_home / "harnesses/pi/keybindings.json").write_text('{"app.tree.foldOrUp": ["alt+left"]}')
    (source_home / "skills/uv/SKILL.md").write_text("---\nname: uv\ndescription: d\n---\nBody\n")
    (source_home / "commands/foo.md").write_text("---\ndescription: foo\n---\nRun foo.\n")
    (source_home / "agents/reviewer.md").write_text("---\nname: reviewer\ndescription: r\ntools: Read\n---\nBody.\n")
    (source_home / "harnesses/opencode/plugins/shared.js").write_text("// plugin")
    (source_home / "harnesses/goose/custom_providers/glm.json").write_text('{"name": "glm"}')
    (source_home / "harnesses/gemini/settings.json").write_text('{"model": "gemini"}')
    (source_home / "harnesses/claude/settings.json").write_text('{"permissions": {"allow": []}}')


@pytest.mark.parametrize("harness,step,target", FILE_LINK_STEPS)
def test_conflict_without_force_is_skipped(source_home: Path, isolated_home: Path, harness: str, step: str, target: str):
    _seed(source_home, harness, step)
    args = ["--source", str(source_home)]
    runner = CliRunner()
    assert runner.invoke(agent_config_app, [*args, "sync", harness]).exit_code == 0, harness
    _edited(isolated_home / target, "hand edited\n")
    result = runner.invoke(agent_config_app, [*args, "sync", harness, step])
    assert result.exit_code == 1, result.output
    assert "skipped" in result.output
    assert (isolated_home / target).read_text() in ("hand edited\n", "hand edited") or (isolated_home / target).is_symlink()


@pytest.mark.parametrize("harness,step,target", FILE_LINK_STEPS)
def test_force_resolves_every_conflict(source_home: Path, isolated_home: Path, harness: str, step: str, target: str):
    _seed(source_home, harness, step)
    args = ["--source", str(source_home)]
    runner = CliRunner()
    assert runner.invoke(agent_config_app, [*args, "sync", harness]).exit_code == 0, harness
    _edited(isolated_home / target, "hand edited\n")
    result = runner.invoke(agent_config_app, [*args, "sync", harness, step, "--force"])
    assert result.exit_code == 0, result.output
    assert "skipped" not in result.output
    backups = isolated_home / ".local/state/agent-config/backups"
    assert any(p.is_file() for p in backups.rglob("*")), (harness, step)
