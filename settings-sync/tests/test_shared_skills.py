from pathlib import Path

import pytest
from typer.testing import CliRunner

from settings_sync.cli import agent_config_app
from settings_sync.ownership import sync_generated_symlink
from tests.test_read_only import snapshot


def test_codex_discovers_source_skills_without_claude(source_home: Path, isolated_home: Path):
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "codex", "skills"])
    assert result.exit_code == 0, result.output
    assert not (isolated_home / ".claude").exists()
    skill = source_home / "skills/new-skill/SKILL.md"
    skill.parent.mkdir()
    skill.write_text("New shared skill")
    assert (isolated_home / ".agents/skills/new-skill/SKILL.md").read_text() == "New shared skill"


def test_codex_replaces_managed_legacy_root(source_home: Path, isolated_home: Path):
    shared = source_home / "skills/example"
    shared.mkdir()
    (shared / "SKILL.md").write_text("Shared skill")
    legacy = isolated_home / ".claude/skills"
    legacy.mkdir(parents=True)
    (legacy / "example").symlink_to(shared)
    root = isolated_home / ".agents/skills"
    sync_generated_symlink(root, legacy)
    before = snapshot(legacy)
    runner = CliRunner()
    args = ["--source", str(source_home)]
    before_dry_run = snapshot(isolated_home)
    result = runner.invoke(agent_config_app, [*args, "sync", "codex", "skills", "--dry-run"])
    assert result.exit_code == 1, result.output
    assert root.resolve() == legacy
    assert snapshot(isolated_home) == before_dry_run
    result = runner.invoke(agent_config_app, [*args, "sync", "codex", "skills"])
    assert result.exit_code == 0, result.output
    assert root.resolve() == source_home / "skills"
    assert snapshot(legacy) == before
    result = runner.invoke(agent_config_app, [*args, "check", "codex", "skills"])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("name", ["personal", "example"])
def test_codex_preserves_legacy_local_skill_discovery(source_home: Path, isolated_home: Path, name: str):
    shared = source_home / "skills/example"
    shared.mkdir()
    (shared / "SKILL.md").write_text("Shared skill")
    legacy = isolated_home / ".claude/skills"
    local = legacy / name / "SKILL.md"
    local.parent.mkdir(parents=True)
    local.write_text("Local skill")
    root = isolated_home / ".agents/skills"
    sync_generated_symlink(root, legacy)
    before = snapshot(isolated_home)
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "codex", "skills", "--force"])
    assert result.exit_code == 1, result.output
    assert name in result.output
    assert snapshot(isolated_home) == before
