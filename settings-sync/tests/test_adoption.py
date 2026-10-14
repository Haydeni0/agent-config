import json
from pathlib import Path
import shutil

import pytest
from typer.testing import CliRunner

from settings_sync.cli import agent_config_app
from tests.test_read_only import snapshot


@pytest.mark.parametrize("interrupt", [False, True])
def test_adoption_and_rollback_preserve_runtime(source_home: Path, isolated_home: Path, tmp_path: Path, interrupt: bool):
    source = tmp_path / "external source with spaces"
    source_home.rename(source)
    alias = tmp_path / "source alias"
    alias.symlink_to(source)
    source_skill = source / "skills/example"
    source_skill.mkdir()
    (source_skill / "SKILL.md").write_text("---\nname: example\ndescription: shared\n---\nShared skill\n")
    shared = isolated_home / ".claude/skills/example"
    shutil.copytree(source_skill, shared)
    sentinels = (
        ".claude/skills/synced/cache/SKILL.md", ".claude/skills/personal/SKILL.md",
        ".claude/projects/session.json", ".claude/plugins/cache/local/state",
        ".codex/auth.json", ".codex/sessions/old-session", ".pi/agent/auth.json",
    )
    for name in sentinels:
        path = isolated_home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Synthetic preserved state")
    original = isolated_home / ".codex/config.toml"
    original.write_text('[projects."/personal"]\ntrust_level="trusted"\n')
    before = snapshot(isolated_home)
    backup = tmp_path / "rollback"
    shutil.copytree(isolated_home, backup, symlinks=True)
    shared.rename(tmp_path / "prior-shared-skill")
    pointer = isolated_home / ".config/agent-config/config.toml"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(f"source = {json.dumps(str(alias))}\n")
    if interrupt:
        (source / "harnesses/pi/settings.json").write_text("[broken")
    runner = CliRunner()
    result = runner.invoke(agent_config_app, ["sync"])
    assert result.exit_code == (1 if interrupt else 0), result.output
    for name in sentinels:
        assert (isolated_home / name).read_text() == "Synthetic preserved state"
    if not interrupt:
        assert runner.invoke(agent_config_app, ["sync"]).exit_code == 0
        assert runner.invoke(agent_config_app, ["check"]).exit_code == 0
        assert runner.invoke(agent_config_app, ["doctor"]).exit_code == 0
        (source / "rules/global.md").write_text("Changed rule\n")
        assert runner.invoke(agent_config_app, ["sync"]).exit_code == 0
        assert (isolated_home / ".codex/AGENTS.md").read_text().endswith("Changed rule\n")
        (shared / "SKILL.md").write_text("Source edit through alias")
        assert (source_skill / "SKILL.md").read_text() == "Source edit through alias"
    shutil.rmtree(isolated_home)
    shutil.copytree(backup, isolated_home, symlinks=True)
    assert snapshot(isolated_home) == before


def test_foreign_shared_skill_collision_preserved(source_home: Path, isolated_home: Path):
    (source_home / "skills/example").mkdir()
    (source_home / "skills/example/SKILL.md").write_text("shared")
    existing = isolated_home / ".claude/skills/example/SKILL.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("personal")
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "claude", "links", "--force"])
    assert result.exit_code == 1
    assert existing.read_text() == "personal"
