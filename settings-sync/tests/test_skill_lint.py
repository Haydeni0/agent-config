"""Lint scope: findings warn opencode without stopping its other steps (REQ-HARNESS-08)."""

from pathlib import Path

from typer.testing import CliRunner

from settings_sync.cli import agent_config_app


def test_sync_opencode_reports_lint_and_writes_configs(source_home: Path, isolated_home: Path) -> None:
    """S39: whole-harness opencode sync warns on lint, exits 1, still writes opencode.json and AGENTS.md."""
    (source_home / "skills/broken").mkdir(parents=True)
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "opencode"])
    assert result.exit_code == 1, result.output
    assert "broken" in result.output
    assert (isolated_home / ".config/opencode/opencode.json").is_file()
    assert (isolated_home / ".config/opencode/AGENTS.md").is_file()


def test_doctor_opencode_lists_lint_and_pi_does_not(source_home: Path, isolated_home: Path) -> None:
    """S40: doctor lists the opencode finding; doctor pi does not."""
    (source_home / "skills/broken").mkdir(parents=True)
    runner = CliRunner()
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "doctor", "opencode"])
    assert "missing SKILL.md" in result.output
    result = runner.invoke(agent_config_app, ["--source", str(source_home), "doctor", "pi"])
    # pi symlinks the skill directory, so the name appears in path output; the lint finding does not.
    assert "missing SKILL.md" not in result.output
