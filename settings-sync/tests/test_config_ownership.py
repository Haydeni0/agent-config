from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from settings_sync.cli import app
from settings_sync.merging import sync_json_defaults
from settings_sync.sync import Status


@pytest.mark.parametrize("harness,step,source,target", [
    ("pi", "config", "harnesses/pi/settings.json", ".pi/agent/settings.json"),
    ("agy", "settings", "harnesses/gemini/settings.json", ".gemini/antigravity-cli/settings.json"),
    ("opencode", "config", "harnesses/opencode/opencode.json", ".config/opencode/opencode.json"),
    ("goose", "config", "harnesses/goose/config.yaml", ".config/goose/config.yaml"),
])
@pytest.mark.parametrize("invalid_side", ["source", "target"])
def test_invalid_mapping_preserves_target(source_home: Path, isolated_home: Path, harness: str, step: str, source: str, target: str, invalid_side: str):
    installed = isolated_home / target
    installed.parent.mkdir(parents=True)
    installed.write_text('{}')
    (source_home / source if invalid_side == "source" else installed).write_text('[broken')
    before = installed.read_bytes()
    result = CliRunner().invoke(app, ["--source", str(source_home), harness, step, "--force"])
    assert result.exit_code == 1, result.output
    assert installed.read_bytes() == before


def test_removed_template_key_retained_and_arrays_replace(tmp_path: Path):
    target = tmp_path / "settings.json"
    assert sync_json_defaults(target, '{"array":[1],"retained":true}').status == Status.CREATED
    assert sync_json_defaults(target, '{"array":[2]}').status == Status.REPLACED
    import json
    assert json.loads(target.read_text()) == {"array": [2], "retained": True}


def test_native_edit_during_merge_preserved(tmp_path: Path, mocker: MockerFixture):
    target = tmp_path / "settings.json"
    target.write_text('{"original":true}')
    original_read = Path.read_text
    def read_then_native_edit(path: Path, *args: object, **kwargs: object) -> str:
        content = original_read(path)
        if path == target:
            target.write_text('{"native":"changed"}')
        return content
    mocker.patch.object(Path, "read_text", read_then_native_edit)
    result = sync_json_defaults(target, '{"managed":true}')
    assert result.status == Status.FAILED
    assert target.read_bytes() == b'{"native":"changed"}'


def test_declared_null_is_installed(tmp_path: Path):
    import json
    target = tmp_path / "settings.json"
    sync_json_defaults(target, '{"explicit_null":null}')
    assert json.loads(target.read_text()) == {"explicit_null": None}
