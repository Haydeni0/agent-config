"""Force semantics: what --force must and must not override (REQ-SYNC-02, REQ-SYNC-12)."""

import json
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


DROP_KEY_PARAMS = [
    # (harness, step, template, target, declare_body, drop_body, entry)
    ("agy", "settings", "harnesses/gemini/settings.json", ".gemini/antigravity-cli/settings.json",
     '{"model": "shared", "extra": 1}', '{"model": "shared"}', None),
    ("agy", "mcp", None, ".gemini/antigravity/mcp_config.json", None, None, "AGY_MCP_ENTRY"),
    ("goose", "config", "harnesses/goose/config.yaml", ".config/goose/config.yaml",
     "model: shared\nextra: 1\n", "model: shared\n", None),
    ("opencode", "tui", "harnesses/opencode/tui.json", ".config/opencode/tui.json",
     '{"$schema": "https://opencode.ai/tui.json", "extra": 1}', '{"$schema": "https://opencode.ai/tui.json"}', None),
    ("opencode", "config", "harnesses/opencode/opencode.json", ".config/opencode/opencode.json",
     '{"$schema": "https://opencode.ai/config.json", "extra": 1}', '{"$schema": "https://opencode.ai/config.json"}', None),
    ("pi", "config", "harnesses/pi/settings.json", ".pi/agent/settings.json",
     '{"skills": ["~/.claude/skills"], "extra": 1}', '{"skills": ["~/.claude/skills"]}', None),
    ("pi", "mcp", "harnesses/pi/mcp.json", ".pi/agent/mcp.json",
     '{"mcpServers": {"codegraph": {"command": "codegraph", "args": ["serve", "--mcp"], "exposure": "direct"}}, "extra": 1}',
     '{"mcpServers": {"codegraph": {"command": "codegraph", "args": ["serve", "--mcp"], "exposure": "direct"}}}', None),
    ("codex", "config", "harnesses/codex/config.toml", ".codex/config.toml",
     'model = "shared"\nextra = 1\n', 'model = "shared"\n', None),
    ("claude", "config", "harnesses/claude/settings.json", ".claude/settings.json",
     '{"permissions": {"defaultMode": "default"}, "extra": 1}', '{"permissions": {"defaultMode": "default"}}', None),
    ("codegraph", "claude-mcp", None, ".claude.json", None, None, "CLAUDE_MCP_ENTRY"),
]


def _patch_entry(monkeypatch: pytest.MonkeyPatch, name: str, extra: bool) -> None:
    import settings_sync.codegraph as codegraph

    entry = dict(getattr(codegraph, name))
    if extra:
        entry["extra"] = 1
    else:
        entry.pop("extra", None)
    monkeypatch.setattr(codegraph, name, entry)


def _declare_key(source_home: Path, monkeypatch: pytest.MonkeyPatch, template: str | None, entry: str | None, declare: str | None) -> None:
    if template is None:
        _patch_entry(monkeypatch, entry, extra=True)
    else:
        (source_home / template).write_text(declare)


def _drop_key(source_home: Path, monkeypatch: pytest.MonkeyPatch, template: str | None, entry: str | None, drop: str | None) -> None:
    if template is None:
        _patch_entry(monkeypatch, entry, extra=False)
    else:
        (source_home / template).write_text(drop)




def _load_installed(installed: Path):
    if installed.suffix == ".json":
        return json.loads(installed.read_text())
    if installed.suffix == ".yaml":
        import yaml
        return yaml.safe_load(installed.read_text())
    import tomllib
    return tomllib.loads(installed.read_text())


def _edit_extra(installed: Path, value) -> None:
    if installed.suffix == ".json":
        data = json.loads(installed.read_text())
        data["extra"] = value
        installed.write_text(json.dumps(data, indent=2))
    elif installed.suffix == ".yaml":
        import yaml
        data = yaml.safe_load(installed.read_text())
        data["extra"] = value
        installed.write_text(yaml.safe_dump(data, sort_keys=False))
    else:
        import tomlkit
        doc = tomlkit.parse(installed.read_text())
        doc["extra"] = value
        installed.write_text(tomlkit.dumps(doc))

@pytest.mark.parametrize("harness,step,template,target,declare,drop,entry", DROP_KEY_PARAMS)
def test_edited_dropped_key_warns_without_force(source_home: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch, harness: str, step: str, template: str | None, target: str, declare: str, drop: str, entry: str | None) -> None:
    """S28: without force an edited dropped key is kept and warned, exit 1."""
    args = ["--source", str(source_home)]
    runner = CliRunner()
    _declare_key(source_home, monkeypatch, template, entry, declare)
    first = runner.invoke(agent_config_app, [*args, "sync", harness, step])
    assert first.exit_code == 0, (harness, first.output)
    installed = isolated_home / target
    _edit_extra(installed, "edited")
    _drop_key(source_home, monkeypatch, template, entry, drop)
    result = runner.invoke(agent_config_app, [*args, "sync", harness, step])
    assert result.exit_code == 1, (harness, result.output)
    assert "warned" in result.output and "extra" in result.output
    assert _load_installed(installed)["extra"] == "edited"


@pytest.mark.parametrize("harness,step,template,target,declare,drop,entry", DROP_KEY_PARAMS)
def test_force_removes_edited_dropped_key(source_home: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch, harness: str, step: str, template: str | None, target: str, declare: str, drop: str, entry: str | None) -> None:
    """S29: --force backs up the file and removes the edited dropped key, exit 0."""
    args = ["--source", str(source_home)]
    runner = CliRunner()
    _declare_key(source_home, monkeypatch, template, entry, declare)
    first = runner.invoke(agent_config_app, [*args, "sync", harness, step])
    assert first.exit_code == 0, (harness, first.output)
    installed = isolated_home / target
    _edit_extra(installed, "edited")
    _drop_key(source_home, monkeypatch, template, entry, drop)
    result = runner.invoke(agent_config_app, [*args, "sync", harness, step, "--force"])
    assert result.exit_code == 0, (harness, result.output)
    assert "extra" not in installed.read_text()
    backups = isolated_home / ".local/state/agent-config/backups"
    assert any(path.is_file() for path in backups.rglob("*"))
