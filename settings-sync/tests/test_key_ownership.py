"""Key-level template ownership: dropped keys removed when unedited (REQ-SYNC-14)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from settings_sync.cli import agent_config_app


def test_untracked_key_never_removed_or_warned(source_home: Path, isolated_home: Path) -> None:
    """S8: a key no template declared under key tracking stays, silently, exit 0."""
    target = isolated_home / ".gemini" / "antigravity-cli" / "settings.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"model": "shared", "nativeOnly": "keep"}))
    result = CliRunner().invoke(
        agent_config_app, ["--source", str(source_home), "sync", "agy", "settings"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(target.read_text())["nativeOnly"] == "keep"
    assert "nativeOnly" not in result.output
