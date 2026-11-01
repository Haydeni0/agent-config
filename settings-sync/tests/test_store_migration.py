"""v1 -> v2 ownership store migration (REQ-SYNC-06, REQ-SYNC-11, REQ-SYNC-14)."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from settings_sync.cli import agent_config_app


def write_v1_store(home: Path, entries: list[dict[str, str]]) -> Path:
    """Write a literal v1 managed.json; the v1 format is frozen history."""
    store = home / ".local" / "state" / "agent-config" / "managed.json"
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps({"version": 1, "entries": entries}, indent=2) + "\n")
    return store


def test_v1_store_syncs_without_error(source_home: Path, isolated_home: Path) -> None:
    """A literal v1 store loads; every slice must keep v1 homes syncing cleanly."""
    (source_home / "rules").mkdir(parents=True, exist_ok=True)
    (source_home / "rules/global.md").write_text("# Rules\n")
    write_v1_store(isolated_home, [])
    result = CliRunner().invoke(
        agent_config_app, ["--source", str(source_home), "sync", "codex", "agents-md"]
    )
    assert result.exit_code == 0, result.output
    assert (isolated_home / ".codex" / "AGENTS.md").is_file()


def write_v1_snapshot(home: Path, target: str, groups: dict) -> Path:
    directory = home / ".local" / "state" / "agent-config" / "hooks"
    directory.mkdir(parents=True, exist_ok=True)
    snapshot = directory / (hashlib.sha256(target.encode()).hexdigest() + ".json")
    snapshot.write_text(json.dumps({"version": 1, "target": target, "hooks": groups}))
    return snapshot


def test_v1_entry_prunes_after_source_removal(source_home: Path, isolated_home: Path) -> None:
    """S17: a v1-recorded command prunes when its source is deleted."""
    (source_home / "commands" / "managed.md").write_text("---\ndescription: managed\n---\nBody\n")
    args = ["--source", str(source_home)]
    runner = CliRunner()
    assert runner.invoke(agent_config_app, [*args, "sync", "opencode", "commands"]).exit_code == 0
    target = isolated_home / ".config/opencode/commands/managed.md"
    destination = str(target)
    target.unlink()
    write_v1_store(isolated_home, [
        {"source_id": "commands/managed.md", "destination": destination,
         "kind": "file", "fingerprint": hashlib.sha256(b"---\ndescription: managed\n---\nBody\n").hexdigest()}
    ])
    (source_home / "commands" / "managed.md").unlink()
    result = runner.invoke(agent_config_app, [*args, "sync", "opencode", "commands"])
    assert result.exit_code == 0, result.output
    assert not target.exists()


def test_migration_persists_v2_and_removes_snapshots(source_home: Path, isolated_home: Path) -> None:
    """S18: after any applying sync, managed.json is version 2 and no snapshot files remain."""
    target = isolated_home / ".claude" / "settings.json"
    write_v1_snapshot(isolated_home, str(target), {"PreToolUse": []})
    write_v1_store(isolated_home, [])
    (source_home / "harnesses" / "claude" / "settings.json").write_text(json.dumps({"hooks": {}}))
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "claude", "config"])
    assert result.exit_code == 0, result.output
    store = json.loads((isolated_home / ".local/state/agent-config/managed.json").read_text())
    assert store["version"] == 2
    assert not list((isolated_home / ".local/state/agent-config/hooks").glob("*.json"))


def test_snapshot_folds_into_hook_reconcile(source_home: Path, isolated_home: Path) -> None:
    """S19: foreign F and adopted G recorded only in a v1 snapshot reconcile to [F, G']."""
    target = isolated_home / ".claude" / "settings.json"
    target.parent.mkdir(parents=True)
    foreign = {"matcher": "Bash", "hooks": [{"type": "command", "command": "local-policy"}]}
    adopted = {"matcher": "Bash", "hooks": [{"type": "command", "command": "shared-policy"}]}
    target.write_text(json.dumps({"hooks": {"PreToolUse": [foreign, adopted]}, "native": True}))
    write_v1_snapshot(isolated_home, str(target), {"PreToolUse": [adopted]})
    updated = {"matcher": "Bash", "hooks": [{"type": "command", "command": "updated-policy"}]}
    (source_home / "harnesses" / "claude" / "settings.json").write_text(
        json.dumps({"hooks": {"PreToolUse": [updated]}})
    )
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "claude", "config"])
    assert result.exit_code == 0, result.output
    assert json.loads(target.read_text())["hooks"]["PreToolUse"] == [foreign, updated]


def test_corrupt_snapshot_fails_whole_run(source_home: Path, isolated_home: Path) -> None:
    """S20: a corrupt snapshot blocks everything, targets byte-identical, message names the file."""
    target = isolated_home / ".claude" / "settings.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"native": True}))
    before = target.read_bytes()
    snapshot = write_v1_snapshot(isolated_home, str(target), {})
    snapshot.write_text("{")
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "claude", "config"])
    assert result.exit_code == 1
    assert snapshot.name in result.output or snapshot.name in (result.stderr or "")
    assert "restore" in result.output
    assert target.read_bytes() == before
    assert snapshot.read_text() == "{"


def test_preview_leaves_v1_store_and_snapshots_byte_identical(source_home: Path, isolated_home: Path) -> None:
    """S21 (migration halves): check and --dry-run exit 0 on a synced v1 home without writing."""
    args = ["--source", str(source_home)]
    runner = CliRunner()
    assert runner.invoke(agent_config_app, [*args, "sync"]).exit_code == 0
    target = isolated_home / ".claude" / "settings.json"
    write_v1_snapshot(isolated_home, str(target), {})
    store_path = isolated_home / ".local/state/agent-config/managed.json"
    data = json.loads(store_path.read_text())
    recorded = [
        {"source_id": item["source_id"], "destination": item["destination"],
         "kind": "file" if item in data["files"] else "symlink", "fingerprint": item["fingerprint"]}
        for item in [*data.get("files", []), *data.get("symlinks", [])]
    ]
    assert recorded
    store_path.write_text(json.dumps({"version": 1, "entries": recorded}, indent=2) + "\n")
    snapshot = write_v1_snapshot(isolated_home, str(target), {})
    before_store = store_path.read_bytes()
    before_snapshot = snapshot.read_bytes()
    for command in (["check"], ["sync", "--dry-run"]):
        result = runner.invoke(agent_config_app, [*args, *command])
        assert result.exit_code == 0, result.output
    assert store_path.read_bytes() == before_store
    assert snapshot.read_bytes() == before_snapshot


def test_v2_record_wins_over_stale_snapshot(source_home: Path, isolated_home: Path) -> None:
    """S22: an interrupted migration's leftover snapshot is discarded, not re-folded."""
    target = isolated_home / ".claude" / "settings.json"
    target.parent.mkdir(parents=True)
    current = {"matcher": "Bash", "hooks": [{"type": "command", "command": "current"}]}
    target.write_text(json.dumps({"hooks": {"PreToolUse": [current]}}))
    desired = {"matcher": "Bash", "hooks": [{"type": "command", "command": "current"}]}
    args = ["--source", str(source_home)]
    (source_home / "harnesses" / "claude" / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [desired]}}))
    runner = CliRunner()
    assert runner.invoke(agent_config_app, [*args, "sync", "claude", "config"]).exit_code == 0
    store_path = isolated_home / ".local/state/agent-config/managed.json"
    stale = write_v1_snapshot(isolated_home, str(target), {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "stale"}]}
    ]})
    result = runner.invoke(agent_config_app, [*args, "sync", "claude", "config"])
    assert result.exit_code == 0, result.output
    assert not stale.exists()
    assert json.loads(target.read_text())["hooks"]["PreToolUse"] == [current]


@pytest.mark.parametrize("store_text", ["broken", '{"version": 3, "entries": []}', '{"version": 2, "files": "nope"}'])
def test_invalid_store_blocks_everything(source_home: Path, isolated_home: Path, store_text: str) -> None:
    """S23: unparseable, unknown-version, or malformed v2 stores fail before any write."""
    store = isolated_home / ".local" / "state" / "agent-config" / "managed.json"
    store.parent.mkdir(parents=True)
    store.write_text(store_text)
    (isolated_home / ".no-mistakes").mkdir()
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "no-mistakes"])
    assert result.exit_code == 1
    assert "restore" in result.output
    # S23's wording: every target and managed.json byte-identical. Compare only
    # those - the engine's own sync.lock under the state dir is exempt, because
    # the lock acquire precedes the load that fails, so a fresh lock file is
    # engine bookkeeping, not a write to any target.
    assert store.read_text() == store_text
    assert not (isolated_home / ".no-mistakes" / "config.yaml").exists()


@pytest.mark.parametrize("entry", [
    {"source_id": "x", "destination": "/tmp/ok", "kind": "socket", "fingerprint": "a"},
    {"source_id": "x", "destination": "relative/path", "kind": "file", "fingerprint": "a"},
    {"source_id": "x", "destination": "/tmp/../etc", "kind": "file", "fingerprint": "a"},
])
def test_invalid_v1_store_blocks_everything(source_home: Path, isolated_home: Path, entry: dict) -> None:
    """Finding 2: a corrupt v1 store (unknown kind, relative or .. destination)
    fails the run instead of being silently normalized or misfiled."""
    text = json.dumps({"version": 1, "entries": [entry]})
    store = isolated_home / ".local" / "state" / "agent-config" / "managed.json"
    store.parent.mkdir(parents=True)
    store.write_text(text)
    (isolated_home / ".no-mistakes").mkdir()
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "no-mistakes"])
    assert result.exit_code == 1
    assert "restore" in result.output
    assert store.read_text() == text
    assert not (isolated_home / ".no-mistakes" / "config.yaml").exists()
