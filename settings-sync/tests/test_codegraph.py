import json
import platform
from pathlib import Path

import pytest

from settings_sync.codegraph import (
    CODEGRAPH_VERSION,
    claude_mcp_json_path,
    current_platform,
    release_url,
    sync_codegraph_binary,
)
from settings_sync.paths import Paths, resolve_paths
from settings_sync.sync import Status


def _paths(tmp_path: Path, **overrides) -> Paths:
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    return resolve_paths(claude_dir=source, codegraph_dir=tmp_path / "cg", **overrides)


def _fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    return home


def _install_fake_version(paths: Paths, version: str = CODEGRAPH_VERSION) -> Path:
    launcher = paths.codegraph_dir / "versions" / version / "bin" / "codegraph"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("#!/bin/sh\necho 1.6.2\n")
    launcher.chmod(0o755)
    return launcher


def test_release_url_platform_triples(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    for machine, arch in (("x86_64", "x64"), ("amd64", "x64"), ("aarch64", "arm64")):
        monkeypatch.setattr(platform, "machine", lambda m=machine: m)
        assert release_url() == f"https://github.com/colbymchenry/codegraph/releases/download/{CODEGRAPH_VERSION}/codegraph-linux-{arch}.tar.gz"
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(platform, "machine", lambda: "arm64")
    assert release_url().endswith(f"/{CODEGRAPH_VERSION}/codegraph-darwin-arm64.tar.gz")


def test_release_url_rejects_unsupported_platform(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    with pytest.raises(ValueError, match="unsupported platform"):
        release_url()


def test_binary_dry_run_missing_reports_would_create(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    paths = _paths(tmp_path)
    outcomes = sync_codegraph_binary(paths, dry_run=True)
    assert outcomes[0].status == Status.WOULD_CREATE
    assert not (paths.codegraph_dir / "versions").exists()


def test_binary_dry_run_ok_reports_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    home = _fake_home(tmp_path, monkeypatch)
    paths = _paths(tmp_path)
    launcher = _install_fake_version(paths)
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "codegraph").symlink_to(launcher)
    monkeypatch.setenv("PATH", str(bin_dir) + ":")
    outcomes = sync_codegraph_binary(paths, dry_run=True)
    assert outcomes[0].status == Status.UNCHANGED


def test_binary_dry_run_stale_symlink_reports_would_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    home = _fake_home(tmp_path, monkeypatch)
    paths = _paths(tmp_path)
    old = _install_fake_version(paths, "v0.9.0")
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "codegraph").symlink_to(old)
    outcomes = sync_codegraph_binary(paths, dry_run=True)
    assert outcomes[0].status == Status.WOULD_REPLACE


def test_binary_dry_run_off_path_reports_warned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    home = _fake_home(tmp_path, monkeypatch)
    paths = _paths(tmp_path)
    launcher = _install_fake_version(paths)
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "codegraph").symlink_to(launcher)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    outcomes = sync_codegraph_binary(paths, dry_run=True)
    assert outcomes[0].status == Status.WARNED


def test_binary_dry_run_shadowed_reports_warned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    home = _fake_home(tmp_path, monkeypatch)
    paths = _paths(tmp_path)
    launcher = _install_fake_version(paths)
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "codegraph").symlink_to(launcher)
    other = tmp_path / "bin"
    other.mkdir()
    (other / "codegraph").write_text("#!/bin/sh\n")
    (other / "codegraph").chmod(0o755)
    monkeypatch.setenv("PATH", str(other) + ":" + str(bin_dir) + ":")
    outcomes = sync_codegraph_binary(paths, dry_run=True)
    assert outcomes[0].status == Status.WARNED


def test_binary_real_sync_installs_and_prunes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    home = _fake_home(tmp_path, monkeypatch)
    paths = _paths(tmp_path)
    _install_fake_version(paths, "v0.9.0")  # stale version dir to prune
    installed = {}

    def fake_download(url: str, version_dir: Path) -> None:
        installed["url"] = url
        launcher = version_dir / "bin" / "codegraph"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text("#!/bin/sh\necho 1.6.2\n")
        launcher.chmod(0o755)

    monkeypatch.setattr("settings_sync.codegraph.download_and_extract", fake_download)
    outcomes = sync_codegraph_binary(paths, dry_run=False)
    assert outcomes[0].status == Status.CREATED
    assert installed["url"] == release_url()
    bin_dir = home / ".local" / "bin"
    assert (bin_dir / "codegraph").resolve() == (paths.codegraph_dir / "versions" / CODEGRAPH_VERSION / "bin" / "codegraph").resolve()
    assert (paths.codegraph_dir / "current").is_symlink()
    assert not (paths.codegraph_dir / "versions" / "v0.9.0").exists()


def test_binary_real_sync_skips_when_current(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    home = _fake_home(tmp_path, monkeypatch)
    paths = _paths(tmp_path)
    launcher = _install_fake_version(paths)
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "codegraph").symlink_to(launcher)

    def fail_download(url: str, version_dir: Path) -> None:
        raise AssertionError("download must not run when the pinned version is installed")

    monkeypatch.setattr("settings_sync.codegraph.download_and_extract", fail_download)
    _install_fake_version(paths, "v0.9.1")  # pruned even on the skip path
    outcomes = sync_codegraph_binary(paths, dry_run=False)
    assert outcomes[0].status == Status.UNCHANGED
    assert not (paths.codegraph_dir / "versions" / "v0.9.1").exists()


def test_binary_real_sync_never_warns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    home = _fake_home(tmp_path, monkeypatch)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # .local/bin off PATH
    paths = _paths(tmp_path)

    def fake_download(url: str, version_dir: Path) -> None:
        launcher = version_dir / "bin" / "codegraph"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text("#!/bin/sh\n")
        launcher.chmod(0o755)

    monkeypatch.setattr("settings_sync.codegraph.download_and_extract", fake_download)
    outcomes = sync_codegraph_binary(paths, dry_run=False)
    assert all(o.status not in (Status.WARNED, Status.WOULD_CREATE, Status.WOULD_REPLACE) for o in outcomes)


def test_claude_mcp_json_path_with_and_without_profile_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    paths = _paths(tmp_path)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert claude_mcp_json_path(paths) == paths.claude_home.parent / ".claude.json"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "profile"))
    profile_paths = resolve_paths(claude_dir=tmp_path / "source")
    assert claude_mcp_json_path(profile_paths) == profile_paths.claude_home / ".claude.json"


def test_claude_mcp_sets_entry_and_preserves_foreign_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import sync_claude_mcp

    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    paths = _paths(tmp_path)
    target = claude_mcp_json_path(paths)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "projects": {"/work": {"allowedTools": ["Bash"]}},
        "oauthAccount": {"email": "user@example.com"},
        "mcpServers": {"other": {"type": "stdio", "command": "other"}},
    }))
    outcomes = sync_claude_mcp(paths, dry_run=False)
    assert outcomes[0].status in (Status.CREATED, Status.REPLACED)
    data = json.loads(target.read_text())
    assert data["mcpServers"]["codegraph"] == {
        "type": "stdio", "command": "codegraph", "args": ["serve", "--mcp"], "alwaysLoad": True,
    }
    assert data["projects"]["/work"]["allowedTools"] == ["Bash"]
    assert data["oauthAccount"] == {"email": "user@example.com"}
    assert data["mcpServers"]["other"]["command"] == "other"


def test_claude_mcp_idempotent_second_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import sync_claude_mcp

    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    paths = _paths(tmp_path)
    sync_claude_mcp(paths, dry_run=False)
    before = claude_mcp_json_path(paths).read_text()
    outcomes = sync_claude_mcp(paths, dry_run=False)
    assert outcomes[0].status == Status.UNCHANGED
    assert claude_mcp_json_path(paths).read_text() == before


def test_claude_mcp_creates_absent_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import sync_claude_mcp

    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    paths = _paths(tmp_path)
    outcomes = sync_claude_mcp(paths, dry_run=False)
    target = claude_mcp_json_path(paths)
    assert target.is_file()
    assert json.loads(target.read_text())["mcpServers"]["codegraph"]["command"] == "codegraph"


def test_claude_mcp_refuses_unparseable_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import sync_claude_mcp

    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    paths = _paths(tmp_path)
    target = claude_mcp_json_path(paths)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{not json")
    outcomes = sync_claude_mcp(paths, dry_run=False)
    assert outcomes[0].status == Status.FAILED
    assert "could not merge JSON configuration" in outcomes[0].detail
    assert target.read_text() == "{not json"
