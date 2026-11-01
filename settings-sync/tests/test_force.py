"""Force semantics: what --force must and must not override (REQ-SYNC-02, REQ-SYNC-12)."""

from pathlib import Path

from typer.testing import CliRunner

from settings_sync.cli import agent_config_app


def _synced_commands(source: Path, home: Path) -> tuple[Path, Path]:
    (source / "commands" / "managed.md").write_text("---\ndescription: managed\n---\nBody\n")
    args = ["--source", str(source)]
    result = CliRunner().invoke(agent_config_app, [*args, "sync", "opencode", "commands"])
    assert result.exit_code == 0, result.output
    return (home / ".config" / "opencode" / "commands"), args


def test_edited_managed_orphan_preserved_under_force(source_home: Path, isolated_home: Path) -> None:
    """S33: an edited managed orphan is warned and preserved, even under --force (REQ-SYNC-12)."""
    target, args = _synced_commands(source_home, isolated_home)
    (source_home / "commands" / "managed.md").unlink()
    (target / "managed.md").write_text("local edit\n")
    result = CliRunner().invoke(agent_config_app, [*args, "sync", "opencode", "commands", "--force"])
    assert result.exit_code == 1, result.output
    assert (target / "managed.md").read_text() == "local edit\n"
    assert "warned" in result.output
