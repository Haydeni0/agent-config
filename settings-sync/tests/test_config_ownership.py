import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from settings_sync.cli import agent_config_app


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
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", harness, step, "--force"])
    assert result.exit_code == 1, result.output
    assert installed.read_bytes() == before


def test_declared_null_is_installed(isolated_home: Path) -> None:
    from settings_sync.actions import MergedConfig, Mode
    from settings_sync.executor import execute
    from settings_sync.merging import JsonCodec
    from settings_sync.ownership import OwnershipStore

    target = isolated_home / "settings.json"
    store = OwnershipStore()
    store.load(Mode.APPLY)
    execute([MergedConfig(target, JsonCodec(), {"explicit_null": None})], Mode.APPLY, store)
    assert json.loads(target.read_text()) == {"explicit_null": None}
