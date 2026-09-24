import os
import pathlib
from typer.testing import CliRunner

from settings_sync.agy import sync_agy_agents_md, sync_agy_settings, sync_agy_skills
from settings_sync.cli import Paths, app
from settings_sync.sync import Status


def test_sync_agy_settings(tmp_path: pathlib.Path):
    source = tmp_path / "gemini" / "settings.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"model": "gemini-3.7-flash"}\n')
    target = tmp_path / "antigravity-cli" / "settings.json"

    outcome = sync_agy_settings(target, source)

    assert outcome.status == Status.CREATED
    assert target.is_file()
    assert '"model": "gemini-3.7-flash"' in target.read_text()


def test_sync_agy_agents_md(tmp_path: pathlib.Path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# Rules\nSee @skills/uv for info.\n")
    target = tmp_path / "AGENTS.md"

    outcome = sync_agy_agents_md(target, claude_md)

    assert outcome.status == Status.CREATED
    assert target.is_file()
    assert "the `uv` skill" in target.read_text()


def test_sync_agy_skills_symlinks(tmp_path: pathlib.Path):
    source_dir = tmp_path / "claude" / "skills"
    (source_dir / "uv").mkdir(parents=True)
    (source_dir / "uv" / "SKILL.md").write_text("---\nname: uv\ndescription: d\n---\nBody\n")
    (source_dir / "pytest").mkdir(parents=True)
    (source_dir / "pytest" / "SKILL.md").write_text("---\nname: pytest\ndescription: d\n---\nBody\n")

    target_dir = tmp_path / "gemini" / "skills"

    outcomes = sync_agy_skills(target_dir, source_dir)

    assert len(outcomes) == 2
    assert all(o.status == Status.CREATED for o in outcomes)
    assert (target_dir / "uv").is_symlink()
    assert (target_dir / "pytest").is_symlink()
    assert os.readlink(target_dir / "uv") == "../../claude/skills/uv"


def test_sync_agy_skills_orphan_handling(tmp_path: pathlib.Path):
    source_dir = tmp_path / "claude" / "skills"
    (source_dir / "uv").mkdir(parents=True)
    (source_dir / "uv" / "SKILL.md").write_text("---\nname: uv\ndescription: d\n---\nBody\n")

    target_dir = tmp_path / "gemini" / "skills"
    target_dir.mkdir(parents=True)
    # create orphan
    (target_dir / "old-skill").mkdir(parents=True)

    for force in (False, True):
        outcomes = sync_agy_skills(target_dir, source_dir, force=force)
        assert all(o.path.name != "old-skill" for o in outcomes)
        assert (target_dir / "old-skill").is_dir()
        assert (target_dir / "uv").is_symlink()



def test_sync_agy_skills_dry_run_does_not_create_dir(tmp_path: pathlib.Path):
    source_dir = tmp_path / "claude" / "skills"
    (source_dir / "uv").mkdir(parents=True)
    (source_dir / "uv" / "SKILL.md").write_text("---\nname: uv\ndescription: d\n---\nBody\n")

    target_dir = tmp_path / "gemini" / "skills"

    outcomes = sync_agy_skills(target_dir, source_dir, dry_run=True)
    assert not target_dir.exists()
    assert len(outcomes) == 1
    assert outcomes[0].status == Status.WOULD_CREATE


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

    agy_dir = tmp_path / "gemini" / "config"
    agy_cli_dir = tmp_path / "gemini" / "antigravity-cli"

    result = runner.invoke(app, ["--claude-dir", str(claude), "--agy-dir", str(agy_dir), "--agy-cli-dir", str(agy_cli_dir), "agy"])

    assert result.exit_code == 0
    assert (agy_dir / "AGENTS.md").is_file()
    assert (agy_dir / "skills" / "uv").is_symlink()
    assert (agy_cli_dir / "settings.json").is_file()
    assert '"model": "gemini-3.7-flash"' in (agy_cli_dir / "settings.json").read_text()
