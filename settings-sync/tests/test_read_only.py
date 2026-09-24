from pathlib import Path

import pytest
from typer.testing import CliRunner

from settings_sync.cli import app


def snapshot(root: Path) -> dict[Path, tuple[int, int, str | bytes]]:
    return {path.relative_to(root): (path.lstat().st_mode, path.lstat().st_mtime_ns,
            str(path.readlink()) if path.is_symlink() else path.read_bytes() if path.is_file() else b"")
            for path in root.rglob("*")}


@pytest.mark.parametrize("installed", [False, True])
@pytest.mark.parametrize("flag", ["--check", "--dry-run"])
def test_preview_preserves_home(source_home: Path, isolated_home: Path, installed: bool, flag: str):
    runner = CliRunner()
    args = ["--source", str(source_home)]
    if installed:
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        (source_home / "rules").mkdir(parents=True, exist_ok=True)
        (source_home / "rules/global.md").write_text("Updated shared rules\n")
    before = snapshot(isolated_home)
    result = runner.invoke(app, [*args, flag])
    assert result.exit_code == 1, result.output
    assert snapshot(isolated_home) == before


def test_repository_checkout_sync_and_check(isolated_home: Path):
    import os
    import subprocess
    import sys
    source = Path(__file__).resolve().parents[2]
    sentinel = isolated_home / ".codex/sessions/preserved"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("local session")
    base = [sys.executable, "-c", "from settings_sync.cli import agent_config_main; agent_config_main()", "--source", str(source)]
    for command in ("sync", "sync", "check", "doctor"):
        result = subprocess.run([*base, command], env=os.environ.copy(), capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert sentinel.read_text() == "local session"
