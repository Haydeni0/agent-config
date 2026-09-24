from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from settings_sync.cli import app
from settings_sync.sync import Outcome, Status, sync_json, sync_text, sync_yaml


def test_jsonc_survives_conflicting_destination(tmp_path: Path):
    source = tmp_path / "source"
    (source / "harnesses/opencode").mkdir(parents=True)
    (source / "harnesses/opencode" / "opencode.json").write_text('{"model":"shared"}')
    target = tmp_path / "opencode"
    target.mkdir()
    legacy = target / "opencode.jsonc"
    legacy.write_text('{"model":"legacy"}')
    (target / "opencode.json").write_text('{"model":"local"}')
    result = CliRunner().invoke(app, ["--source", str(source), "--opencode-dir", str(target), "opencode", "config"])
    assert result.exit_code == 1
    assert legacy.read_text() == '{"model":"legacy"}'
    assert (target / "opencode.json").read_text() == '{"model":"local"}'


@pytest.mark.parametrize("flag", ["--check", "--dry-run"])
def test_preview_does_not_create_directories(tmp_path: Path, flag: str):
    source = tmp_path / "source"
    (source / "commands").mkdir(parents=True)
    (source / "commands" / "example.md").write_text("---\ndescription: example\n---\nRun.\n")
    target = tmp_path / "opencode"
    result = CliRunner().invoke(app, ["--source", str(source), "--opencode-dir", str(target), "opencode", "commands", flag])
    assert result.exit_code == 1
    assert not target.exists()


@pytest.mark.parametrize("writer,original,replacement", [(sync_text, "before", "after"), (sync_json, '{"a":1}', '{"a":2}'), (sync_yaml, "a: 1", "a: 2")])
def test_failed_replace_preserves_original(tmp_path: Path, mocker: MockerFixture, writer: Callable[..., Outcome], original: str, replacement: str):
    target = tmp_path / "config"
    target.write_text(original)
    target.chmod(0o640)
    mocker.patch("pathlib.Path.replace", side_effect=OSError("disk unavailable"))
    result = writer(target, replacement, force=True)
    assert result.status == Status.FAILED
    assert target.read_text() == original
    assert target.stat().st_mode & 0o777 == 0o640
    assert list(tmp_path.iterdir()) == [target]


def test_regular_output_rejects_symlink(tmp_path: Path):
    source = tmp_path / "source"
    source.write_text("keep")
    target = tmp_path / "target"
    target.symlink_to(source)
    result = sync_text(target, "replacement", force=True)
    assert result.status == Status.FAILED
    assert source.read_text() == "keep"


def test_jsonc_preview_includes_migration(tmp_path: Path):
    source = tmp_path / "source"
    (source / "harnesses/opencode").mkdir(parents=True)
    (source / "harnesses/opencode" / "opencode.json").write_text('{"model":"shared"}')
    target = tmp_path / "opencode"
    target.mkdir()
    (target / "opencode.json").write_text('{"model":"local"}')
    legacy = target / "opencode.jsonc"
    legacy.write_text('{"local_only":"keep-me"}')
    result = CliRunner().invoke(app, ["--source", str(source), "--opencode-dir", str(target), "opencode", "config", "--check", "--verbose"])
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
    result = CliRunner().invoke(app, ["--source", str(source_home), "opencode", "config", "--force"])
    assert result.exit_code == 1
    assert target.is_dir() if kind == "directory" else target.is_symlink()
    assert not target.with_suffix(".json").exists()


def test_symlink_replace_failure_preserves_old_link(tmp_path: Path, mocker: MockerFixture):
    from settings_sync.sync import sync_symlink
    old = tmp_path / "old"
    old.mkdir()
    new = tmp_path / "new"
    new.mkdir()
    target = tmp_path / "target"
    target.symlink_to(old)
    mocker.patch("pathlib.Path.replace", side_effect=OSError("disk unavailable"))
    result = sync_symlink(target, new, force=True)
    assert result.status == Status.FAILED
    assert target.resolve() == old
    assert set(tmp_path.iterdir()) == {old, new, target}
