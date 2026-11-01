import json
from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from settings_sync.actions import Status
from settings_sync.cli import agent_config_app


def test_jsonc_survives_conflicting_destination(source_home: Path, isolated_home: Path):
    (source_home / "harnesses/opencode/opencode.json").write_text('{"model":"shared"}')
    target = isolated_home / ".config/opencode/opencode.json"
    target.parent.mkdir(parents=True)
    legacy = target.with_suffix(".jsonc")
    legacy.write_text('{"model":"legacy"}')
    target.write_text('{"model":"local"}')
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "opencode", "config"])
    assert result.exit_code == 1
    assert "skipped" in result.output
    assert legacy.read_text() == '{"model":"legacy"}'
    assert target.read_text() == '{"model":"local"}'


def test_jsonc_migrates_under_force(source_home: Path, isolated_home: Path):
    (source_home / "harnesses/opencode/opencode.json").write_text('{"model":"shared"}')
    target = isolated_home / ".config/opencode/opencode.json"
    target.parent.mkdir(parents=True)
    legacy = target.with_suffix(".jsonc")
    legacy.write_text('{"model":"legacy","localOnly":"keep-me"}')
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "opencode", "config", "--force"])
    assert result.exit_code == 0, result.output
    written = json.loads(target.read_text())
    assert written["model"] == "shared"
    assert written["localOnly"] == "keep-me"
    assert not legacy.exists()
    backups = isolated_home / ".local/state/agent-config/backups"
    assert any(p.is_file() for p in backups.rglob("*"))


@pytest.mark.parametrize("command", [["check", "opencode", "commands"], ["sync", "opencode", "commands", "--dry-run"]])
def test_preview_does_not_create_directories(tmp_path: Path, command: list[str]):
    source = tmp_path / "source"
    (source / "commands").mkdir(parents=True)
    (source / "commands" / "example.md").write_text("---\ndescription: example\n---\nRun.\n")
    target = tmp_path / "opencode"
    result = CliRunner().invoke(agent_config_app, ["--source", str(source), "--opencode-dir", str(target), *command])
    assert result.exit_code == 1
    assert not target.exists()


def test_jsonc_preview_includes_migration(tmp_path: Path):
    source = tmp_path / "source"
    (source / "harnesses/opencode").mkdir(parents=True)
    (source / "harnesses/opencode" / "opencode.json").write_text('{"model":"shared"}')
    target = tmp_path / "opencode"
    target.mkdir()
    (target / "opencode.json").write_text('{"model":"local"}')
    legacy = target / "opencode.jsonc"
    legacy.write_text('{"local_only":"keep-me"}')
    result = CliRunner().invoke(agent_config_app, ["--verbose", "--source", str(source), "--opencode-dir", str(target), "check", "opencode", "config"])
    assert result.exit_code == 1
    assert "keep-me" in result.output
    assert legacy.exists()


@pytest.mark.parametrize("kind", ["directory", "broken-link"])
def test_nonregular_jsonc_preserved(source_home: Path, isolated_home: Path, kind: str):
    target = isolated_home / ".config/opencode/opencode.jsonc"
    target.parent.mkdir(parents=True)
    if kind == "directory":
        target.mkdir()
    else:
        target.symlink_to("absent")
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "opencode", "config", "--force"])
    assert result.exit_code == 1
    assert target.is_dir() if kind == "directory" else target.is_symlink()
    assert not target.with_suffix(".json").exists()


def test_symlink_replace_failure_preserves_old_link(isolated_home: Path, mocker: MockerFixture) -> None:
    from settings_sync.actions import Mode, Symlink
    from settings_sync.executor import execute
    from settings_sync.ownership import OwnershipStore

    old = isolated_home / "old"
    old.mkdir()
    new = isolated_home / "new"
    new.mkdir()
    target = isolated_home / "target"
    target.symlink_to(old)
    mocker.patch("pathlib.Path.replace", side_effect=OSError("disk unavailable"))
    store = OwnershipStore()
    store.load(Mode.FORCE)
    outcome = execute([Symlink(target, new)], Mode.FORCE, store)[0]
    assert outcome.status == Status.FAILED
    assert target.resolve() == old.resolve()
