import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from settings_sync.actions import Mode
from settings_sync.cli import agent_config_app
from tests.test_read_only import snapshot


def home_snapshot(home: Path) -> dict:
    """Snapshot excluding the engine's own state dir (lock and store bookkeeping)."""
    return {path: entry for path, entry in snapshot(home).items()
            if not path.parts[:3] == (".local", "state", "agent-config")}


def record_link(home: Path, link: Path, target: Path) -> None:
    from settings_sync.ownership import ManagedEntry, OwnershipStore
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    store = OwnershipStore()
    store.load(Mode.APPLY)
    store.record_symlink(ManagedEntry(f"{link.parent.name}/{link.name}", link, os.readlink(link)))


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
    local = legacy / "synced/bucket/personal/SKILL.md"
    local.parent.mkdir(parents=True)
    local.write_text("Claude-local generated skill")
    root = isolated_home / ".agents/skills"
    record_link(isolated_home, root, legacy)
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
    assert not (root / "synced").exists()
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
    record_link(isolated_home, root, legacy)
    before = home_snapshot(isolated_home)
    runner = CliRunner()
    args = ["--source", str(source_home)]
    result = runner.invoke(agent_config_app, [*args, "sync", "codex", "skills"])
    assert result.exit_code == 1, result.output
    assert name in result.output
    assert home_snapshot(isolated_home) == before
    result = runner.invoke(agent_config_app, [*args, "sync", "codex", "skills", "--force"])
    assert result.exit_code == 0, result.output
    assert root.resolve() == source_home / "skills"
    backups = isolated_home / ".local/state/agent-config/backups"
    assert any(path.is_symlink() for path in backups.rglob("*"))
