from pathlib import Path

import pytest
from typer.testing import CliRunner

from settings_sync.cli import agent_config_app
from tests.test_read_only import snapshot


def test_short_commands_and_read_only_diagnostics(source_home: Path, isolated_home: Path):
    args = ["--source", str(source_home)]
    runner = CliRunner()
    assert runner.invoke(agent_config_app, [*args, "check", "codex"]).exit_code == 1
    result = runner.invoke(agent_config_app, [*args, "sync", "codex"])
    assert result.exit_code == 0, result.output
    assert (isolated_home / ".agents/skills").resolve() == source_home / "skills"
    before = snapshot(isolated_home)
    for command in ("check", "doctor"):
        result = runner.invoke(agent_config_app, [*args, command, "codex"])
        assert result.exit_code == 0, result.output
    assert snapshot(isolated_home) == before


@pytest.mark.parametrize("kind", ["directory", "link"])
def test_shared_skill_root_preserves_foreign_entries(source_home: Path, isolated_home: Path, kind: str):
    target = isolated_home / ".agents/skills"
    target.parent.mkdir()
    foreign = isolated_home / "my-skills"
    foreign.mkdir()
    if kind == "directory":
        target.mkdir()
        (target / "personal").write_text("keep")
    else:
        target.symlink_to(foreign)
    before = snapshot(target.parent)
    runner = CliRunner()
    args = ["--source", str(source_home)]
    result = runner.invoke(agent_config_app, [*args, "sync", "codex", "skills"])
    assert result.exit_code == 1, result.output
    assert snapshot(target.parent) == before
    result = runner.invoke(agent_config_app, [*args, "sync", "codex", "skills", "--force"])
    if kind == "directory":
        assert result.exit_code == 1, result.output
        assert "failed" in result.output
        assert snapshot(target.parent) == before
        assert (target / "personal").read_text() == "keep"
    else:
        assert result.exit_code == 0, result.output
        assert target.resolve() == (source_home / "skills").resolve()
        backups = isolated_home / ".local/state/agent-config/backups"
        assert any(path.is_symlink() for path in backups.rglob("*"))


def test_doctor_reports_required_missing_and_broken_link(source_home: Path, isolated_home: Path):
    (source_home / "harnesses/codex/config.toml").unlink()
    (source_home / "skills/broken").symlink_to(source_home / "vendor/uninitialized")
    before = snapshot(isolated_home)
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "doctor", "codex"])
    assert result.exit_code == 1
    assert "harnesses/codex/config.toml" in result.output
    assert "broken" in result.output
    assert "submodule update" in result.output
    assert snapshot(isolated_home) == before


def test_doctor_reports_missing_hook_runtime(source_home: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('PATH', '')
    before = snapshot(isolated_home)
    result = CliRunner().invoke(agent_config_app, ['--source', str(source_home), 'doctor', 'claude'])
    assert result.exit_code == 1
    assert 'Node.js' in result.output
    assert snapshot(isolated_home) == before
