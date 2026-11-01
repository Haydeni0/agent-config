from pathlib import Path

import pytest
from typer.testing import CliRunner

from settings_sync.cli import agent_config_app, run_all_tools
from settings_sync.paths import Paths
from settings_sync.actions import Status


@pytest.mark.parametrize("harness,steps", [
    ("pi", []), ("goose", []), ("agy", []), ("codex", []), ("no-mistakes", []), ("opencode", ["config"]),
])
def test_config_independent_of_skill_lint(source_home: Path, harness: str, steps: list[str]):
    (source_home / "skills/broken").mkdir(parents=True)
    result = CliRunner().invoke(
        agent_config_app, ["--source", str(source_home), "sync", harness, *steps]
    )
    assert result.exit_code == 0, result.output


def test_opencode_skills_step_reports_lint(source_home: Path, isolated_home: Path):
    (source_home / "skills/broken").mkdir(parents=True)
    result = CliRunner().invoke(
        agent_config_app, ["--source", str(source_home), "sync", "opencode", "skills"]
    )
    assert result.exit_code == 1, result.output
    assert "broken" in result.output
    assert not (isolated_home / ".config" / "opencode").exists()


def test_missing_required_source_errors_and_other_targets_continue(source_home: Path, isolated_home: Path):
    (source_home / "harnesses/pi/settings.json").unlink()
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync"])
    assert result.exit_code == 1, result.output
    assert "required source" in result.output
    assert (isolated_home / ".codex/config.toml").is_file()
    assert not (isolated_home / ".pi/agent/settings.json").exists()


def test_all_skips_omitted_destinations(source_home: Path, tmp_path: Path):
    paths = Paths(source_dir=source_home, opencode_dir=tmp_path / "opencode")
    outcomes, _ = run_all_tools(paths, False, False)
    assert any(outcome.status == Status.CREATED for outcome in outcomes)
    assert not any(outcome.status == Status.FAILED for outcome in outcomes)


def test_codegraph_group_is_first_and_has_three_steps():
    from settings_sync.registry import HARNESSES

    assert HARNESSES[0].name == "codegraph"
    assert [step.name for step in HARNESSES[0].steps] == ["binary", "claude-mcp", "telemetry"]
    assert HARNESSES[0].host == "codegraph"
