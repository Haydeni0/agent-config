from conftest import install_hook_sources
import os
import pathlib

import pytest
from typer.testing import CliRunner

from settings_sync.actions import Mode, Status
from settings_sync.registry import HARNESSES
from settings_sync.agy import plan_agy_settings, plan_agy_skills
from settings_sync.cli import Paths, agent_config_app
from settings_sync.executor import execute
from settings_sync.ownership import OwnershipStore
from settings_sync.paths import resolve_paths




def _apply(plan, paths, mode: Mode):
    store = OwnershipStore()
    store.load(mode)
    return execute(plan(paths), mode, store)

def test_sync_agy_settings(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "harnesses" / "gemini" / "settings.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"model": "gemini-3.7-flash"}\n')
    paths = resolve_paths(HARNESSES, claude_dir=tmp_path / "claude", agy_dir=tmp_path / "gemini" / "config", agy_cli_dir=tmp_path / "antigravity-cli")
    target = paths.agy_cli_dir / "settings.json"

    outcome = _apply(plan_agy_settings, paths, Mode.APPLY)[0]

    assert outcome.status == Status.MERGED
    assert target.is_file()
    assert '"model": "gemini-3.7-flash"' in target.read_text()


def test_sync_agy_skills_symlinks(tmp_path: pathlib.Path):
    source_dir = tmp_path / "claude" / "skills"
    (source_dir / "uv").mkdir(parents=True)
    (source_dir / "uv" / "SKILL.md").write_text("---\nname: uv\ndescription: d\n---\nBody\n")
    (source_dir / "pytest").mkdir(parents=True)
    (source_dir / "pytest" / "SKILL.md").write_text("---\nname: pytest\ndescription: d\n---\nBody\n")

    paths = resolve_paths(HARNESSES, claude_dir=tmp_path / "claude", agy_dir=tmp_path / "gemini" / "config")
    target_dir = paths.agy_dir / "skills"

    outcomes = _apply(plan_agy_skills, paths, Mode.APPLY)

    created = [o for o in outcomes if o.status == Status.CREATED]
    assert len(created) == 2
    assert (target_dir / "uv").is_symlink()
    assert (target_dir / "pytest").is_symlink()
    assert os.readlink(target_dir / "uv") == "../../../claude/skills/uv"


def test_sync_agy_skills_orphan_handling(tmp_path: pathlib.Path):
    source_dir = tmp_path / "claude" / "skills"
    (source_dir / "uv").mkdir(parents=True)
    (source_dir / "uv" / "SKILL.md").write_text("---\nname: uv\ndescription: d\n---\nBody\n")

    paths = resolve_paths(HARNESSES, claude_dir=tmp_path / "claude", agy_dir=tmp_path / "gemini" / "config")
    target_dir = paths.agy_dir / "skills"
    target_dir.mkdir(parents=True)
    # create orphan
    (target_dir / "old-skill").mkdir(parents=True)

    for mode in (Mode.APPLY, Mode.FORCE):
        outcomes = _apply(plan_agy_skills, paths, mode)
        assert all(o.path.name != "old-skill" for o in outcomes)
        assert (target_dir / "old-skill").is_dir()
        assert (target_dir / "uv").is_symlink()



def test_sync_agy_skills_dry_run_does_not_create_dir(tmp_path: pathlib.Path):
    source_dir = tmp_path / "claude" / "skills"
    (source_dir / "uv").mkdir(parents=True)
    (source_dir / "uv" / "SKILL.md").write_text("---\nname: uv\ndescription: d\n---\nBody\n")

    paths = resolve_paths(HARNESSES, claude_dir=tmp_path / "claude", agy_dir=tmp_path / "gemini" / "config")
    target_dir = paths.agy_dir / "skills"

    outcomes = _apply(plan_agy_skills, paths, Mode.DRY_RUN)
    assert not target_dir.exists()
    uv = [o for o in outcomes if o.path.name == "uv"][0]
    assert uv.status == Status.WOULD_CREATE


def test_sync_agy_skills_missing_source_dir(tmp_path: pathlib.Path):
    (tmp_path / "claude").mkdir(parents=True)
    paths = resolve_paths(HARNESSES, claude_dir=tmp_path / "claude", agy_dir=tmp_path / "dst")
    target_dir = paths.agy_dir / "skills"
    target_dir.mkdir(parents=True)
    (target_dir / "existing-file").write_text("keep me")
    with pytest.raises(OSError):
        plan_agy_skills(paths)
    assert (target_dir / "existing-file").exists()


def test_sync_agy_skills_prunes_orphans(tmp_path: pathlib.Path):
    source = tmp_path / "claude"
    source_dir = source / "skills"
    (source_dir / "skill-a").mkdir(parents=True)
    (source_dir / "skill-b").mkdir(parents=True)
    paths = resolve_paths(HARNESSES, claude_dir=source, agy_dir=tmp_path / "dst")
    target_dir = paths.agy_dir / "skills"
    target_dir.mkdir(parents=True)
    (target_dir / "orphan-skill").mkdir(parents=True)
    _apply(plan_agy_skills, paths, Mode.APPLY)
    (source_dir / "skill-a").rmdir()
    outcomes = _apply(plan_agy_skills, paths, Mode.FORCE)
    assert (target_dir / "orphan-skill").is_dir()
    assert not (target_dir / "skill-a").is_symlink()
    assert (target_dir / "skill-b").is_symlink()
    assert any(o.path.name == "skill-a" and o.status == Status.REPLACED for o in outcomes)


runner = CliRunner()


def test_cli_agy_all(tmp_path: pathlib.Path):
    claude = tmp_path / "claude"
    claude.mkdir(parents=True)
    (claude / "rules").mkdir(parents=True, exist_ok=True)
    (claude / "rules/global.md").write_text("# Rules\nSee @skills/uv.\n")
    (claude / "skills" / "uv").mkdir(parents=True)
    (claude / "skills" / "uv" / "SKILL.md").write_text("---\nname: uv\ndescription: d\n---\nBody\n")
    (claude / "harnesses/gemini").mkdir(parents=True)
    (claude / "harnesses/gemini" / "settings.json").write_text('{"model": "gemini-3.7-flash"}\n')

    install_hook_sources(claude)
    agy_dir = tmp_path / "gemini" / "config"
    agy_cli_dir = tmp_path / "gemini" / "antigravity-cli"

    result = runner.invoke(agent_config_app, ["--claude-dir", str(claude), "--agy-dir", str(agy_dir), "--agy-cli-dir", str(agy_cli_dir), "sync", "agy"])

    assert result.exit_code == 0
    assert (agy_dir / "AGENTS.md").is_file()
    assert (agy_dir / "skills" / "uv").is_symlink()
    assert (agy_cli_dir / "settings.json").is_file()
    assert '"model": "gemini-3.7-flash"' in (agy_cli_dir / "settings.json").read_text()
