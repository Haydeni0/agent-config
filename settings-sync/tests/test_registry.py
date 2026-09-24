from pathlib import Path

import pytest
from typer.testing import CliRunner

from settings_sync.cli import app, run_all_tools
from settings_sync.paths import Paths
from settings_sync.sync import Status


@pytest.mark.parametrize("harness,step", [("pi", "config"), ("goose", "config"), ("agy", "settings"), ("no-mistakes", "config"), ("opencode", "config")])
def test_config_independent_of_skill_lint(source_home: Path, harness: str, step: str):
    (source_home / "skills/synced/container").mkdir(parents=True)
    result = CliRunner().invoke(app, ["--source", str(source_home), harness, step])
    assert result.exit_code == 0, result.output


def test_missing_required_source_errors_and_other_targets_continue(source_home: Path, isolated_home: Path):
    (source_home / "harnesses/pi/settings.json").unlink()
    result = CliRunner().invoke(app, ["--source", str(source_home)])
    assert result.exit_code == 1, result.output
    assert "required source" in result.output
    assert (isolated_home / ".codex/config.toml").is_file()
    assert not (isolated_home / ".pi/agent/settings.json").exists()


def test_all_skips_omitted_destinations(source_home: Path, tmp_path: Path):
    paths = Paths(source_dir=source_home, opencode_dir=tmp_path / "opencode")
    outcomes, _ = run_all_tools(paths, False, False)
    assert any(outcome.status == Status.CREATED for outcome in outcomes)
    assert not any(outcome.status == Status.FAILED for outcome in outcomes)
