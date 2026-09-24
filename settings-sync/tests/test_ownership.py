import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from settings_sync.cli import app


def test_source_update_needs_no_force(source_home: Path, isolated_home: Path):
    args = ["--source", str(source_home), "codex", "agents-md"]
    runner = CliRunner()
    assert runner.invoke(app, args).exit_code == 0
    (source_home / "rules").mkdir(parents=True, exist_ok=True)
    (source_home / "rules/global.md").write_text("# Updated\n")
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert (isolated_home / ".codex" / "AGENTS.md").read_text().endswith("# Updated\n")


def test_local_edit_requires_backup_before_force(source_home: Path, isolated_home: Path):
    args = ["--source", str(source_home), "codex", "agents-md"]
    runner = CliRunner()
    assert runner.invoke(app, args).exit_code == 0
    target = isolated_home / ".codex" / "AGENTS.md"
    target.write_text("Local instructions\n")
    assert runner.invoke(app, args).exit_code == 1
    assert target.read_text().endswith("Local instructions\n")
    assert runner.invoke(app, [*args, "--force"]).exit_code == 0
    backups = isolated_home / ".local" / "state" / "agent-config" / "backups"
    assert any(path.is_file() and path.read_text().endswith("Local instructions\n") for path in backups.rglob("*"))


def test_orphan_cleanup_preserves_foreign_files(source_home: Path, isolated_home: Path):
    command = source_home / "commands" / "managed.md"
    command.write_text("---\ndescription: managed\n---\nBody\n")
    args = ["--source", str(source_home), "opencode", "commands"]
    runner = CliRunner()
    assert runner.invoke(app, args).exit_code == 0
    target = isolated_home / ".config" / "opencode" / "commands"
    foreign = target / "personal.md"
    foreign.write_text("My own command\n")
    command.unlink()
    result = runner.invoke(app, [*args, "--force"])
    assert result.exit_code == 0, result.output
    assert foreign.read_text().endswith("My own command\n")
    assert not (target / "managed.md").exists()


def test_corrupt_ownership_prevents_changes(source_home: Path, isolated_home: Path):
    store = isolated_home / ".local" / "state" / "agent-config" / "managed.json"
    store.parent.mkdir(parents=True)
    store.write_text("broken")
    result = CliRunner().invoke(app, ["--source", str(source_home), "codex", "agents-md"])
    assert result.exit_code != 0
    assert not (isolated_home / ".codex" / "AGENTS.md").exists()


@pytest.mark.parametrize("tool,step,source_file,target_file", [
    ("pi", "config", "harnesses/pi/settings.json", ".pi/agent/settings.json"),
    ("agy", "settings", "harnesses/gemini/settings.json", ".gemini/antigravity-cli/settings.json"),
    ("opencode", "config", "harnesses/opencode/opencode.json", ".config/opencode/opencode.json"),
])
def test_json_defaults_keep_local_state(source_home: Path, isolated_home: Path, tool: str, step: str, source_file: str, target_file: str):
    (source_home / source_file).write_text('{"model":"shared","features":{"managed":true}}')
    target = isolated_home / target_file
    target.parent.mkdir(parents=True)
    target.write_text('{"model":"local","features":{"managed":false,"custom":true},"session":"keep"}')
    result = CliRunner().invoke(app, ["--source", str(source_home), tool, step])
    assert result.exit_code == 0, result.output
    content = json.loads(target.read_text())
    assert content["model"] == "shared"
    assert content["features"] == {"managed": True, "custom": True}
    assert content["session"] == "keep"


def test_goose_defaults_keep_local_state(source_home: Path, isolated_home: Path):
    target = isolated_home / ".config" / "goose" / "config.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("GOOSE_TELEMETRY_ENABLED: true\nGOOSE_MODEL: local-model\n")
    result = CliRunner().invoke(app, ["--source", str(source_home), "goose", "config"])
    assert result.exit_code == 0, result.output
    assert "GOOSE_MODEL: local-model" in target.read_text()
    assert "GOOSE_TELEMETRY_ENABLED: false" in target.read_text()


def test_lexical_parent_destination_remains_usable(source_home: Path, isolated_home: Path):
    (isolated_home / "parent").mkdir()
    args = ["--source", str(source_home), "--codex-dir", str(isolated_home / "parent/../codex"), "codex", "agents-md"]
    runner = CliRunner()
    assert runner.invoke(app, args).exit_code == 0
    (source_home / "rules").mkdir(parents=True, exist_ok=True)
    (source_home / "rules/global.md").write_text("Changed\n")
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert (isolated_home / "codex/AGENTS.md").read_text().endswith("Changed\n")


def test_identical_crlf_output_adopted(source_home: Path, isolated_home: Path):
    target = isolated_home / ".codex/AGENTS.md"
    target.parent.mkdir()
    (source_home / "rules").mkdir(parents=True, exist_ok=True)
    (source_home / "rules/global.md").write_text("Rules\n")
    args = ["--source", str(source_home), "codex", "agents-md"]
    runner = CliRunner()
    assert runner.invoke(app, args).exit_code == 0
    target.write_bytes(target.read_text().replace("\n", "\r\n").encode())
    (isolated_home / ".local/state/agent-config/managed.json").unlink()
    assert runner.invoke(app, args).exit_code == 0
    (source_home / "rules").mkdir(parents=True, exist_ok=True)
    (source_home / "rules/global.md").write_text("Changed\n")
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert target.read_text().endswith("Changed\n")
