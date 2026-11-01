"""v1 -> v2 ownership store migration (REQ-SYNC-06, REQ-SYNC-11, REQ-SYNC-14)."""

import json
from pathlib import Path

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
