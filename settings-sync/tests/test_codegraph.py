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
from settings_sync.actions import Status


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


def _agy_paths(tmp_path: Path, **overrides) -> Paths:
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    return resolve_paths(claude_dir=source, agy_dir=tmp_path / "gemini-config", codegraph_dir=tmp_path / "cg", **overrides)


def test_agy_mcp_uses_unified_path_when_migrated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import sync_agy_mcp

    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    paths = _agy_paths(tmp_path)
    paths.agy_dir.mkdir(parents=True)
    (paths.agy_dir / ".migrated").write_text("")
    sync_agy_mcp(paths, dry_run=False)
    target = paths.agy_dir / "mcp_config.json"
    assert target.is_file()
    entry = json.loads(target.read_text())["mcpServers"]["codegraph"]
    assert entry == {"command": "codegraph", "args": ["serve", "--mcp"]}
    assert "type" not in entry


def test_agy_mcp_uses_unified_path_when_file_exists_without_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import sync_agy_mcp

    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    paths = _agy_paths(tmp_path)
    paths.agy_dir.mkdir(parents=True)
    (paths.agy_dir / "mcp_config.json").write_text(json.dumps({"mcpServers": {"other": {"command": "other"}}}))
    sync_agy_mcp(paths, dry_run=False)
    data = json.loads((paths.agy_dir / "mcp_config.json").read_text())
    assert data["mcpServers"]["other"] == {"command": "other"}
    assert data["mcpServers"]["codegraph"]["command"] == "codegraph"


def test_agy_mcp_falls_back_to_legacy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import sync_agy_mcp

    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    paths = _agy_paths(tmp_path)
    paths.agy_dir.mkdir(parents=True)
    sync_agy_mcp(paths, dry_run=False)
    legacy = paths.agy_dir.parent / "antigravity" / "mcp_config.json"
    assert legacy.is_file()
    assert not (paths.agy_dir / "mcp_config.json").exists()


def test_agy_mcp_darwin_writes_absolute_launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import sync_agy_mcp

    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "darwin")
    paths = _agy_paths(tmp_path)
    paths.agy_dir.mkdir(parents=True)
    (paths.agy_dir / ".migrated").write_text("")
    launcher = paths.codegraph_dir / "versions" / CODEGRAPH_VERSION / "bin" / "codegraph"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("#!/bin/sh\n")
    sync_agy_mcp(paths, dry_run=False)
    entry = json.loads((paths.agy_dir / "mcp_config.json").read_text())["mcpServers"]["codegraph"]
    assert entry["command"] == str(launcher)
    assert entry["args"] == ["serve", "--mcp"]


def test_agy_mcp_darwin_missing_binary_uses_pinned_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import sync_agy_mcp

    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "darwin")
    paths = _agy_paths(tmp_path)
    paths.agy_dir.mkdir(parents=True)
    (paths.agy_dir / ".migrated").write_text("")
    sync_agy_mcp(paths, dry_run=False)
    entry = json.loads((paths.agy_dir / "mcp_config.json").read_text())["mcpServers"]["codegraph"]
    assert entry["command"] == str(paths.codegraph_dir / "versions" / CODEGRAPH_VERSION / "bin" / "codegraph")


def test_pi_mcp_merges_and_preserves_user_servers(tmp_path: Path):
    from settings_sync.codegraph import sync_pi_mcp

    (tmp_path / "source").mkdir()
    paths = resolve_paths(claude_dir=tmp_path / "source", pi_dir=tmp_path / "pi", codegraph_dir=tmp_path / "cg")
    target = paths.pi_dir / "mcp.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"mcpServers": {"mine": {"command": "mine"}}}))
    template = paths.source_dir / "harnesses/pi/mcp.json"
    template.parent.mkdir(parents=True)
    template.write_text(json.dumps({
        "mcpServers": {"codegraph": {"command": "codegraph", "args": ["serve", "--mcp"], "exposure": "direct"}}
    }))
    sync_pi_mcp(paths, dry_run=False)
    data = json.loads(target.read_text())
    assert data["mcpServers"]["mine"] == {"command": "mine"}
    entry = data["mcpServers"]["codegraph"]
    assert entry == {"command": "codegraph", "args": ["serve", "--mcp"], "exposure": "direct"}
    assert "type" not in entry


def test_telemetry_dry_run_no_file_reports_would_create(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import sync_codegraph_telemetry

    paths = _paths(tmp_path)
    outcomes = sync_codegraph_telemetry(paths, dry_run=True)
    assert outcomes[0].status == Status.WOULD_CREATE


def test_telemetry_dry_run_stored_optout_reports_unchanged(tmp_path: Path):
    from settings_sync.codegraph import sync_codegraph_telemetry

    paths = _paths(tmp_path)
    target = paths.codegraph_dir / "telemetry.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"enabled": False, "machine_id": None}))
    outcomes = sync_codegraph_telemetry(paths, dry_run=True)
    assert outcomes[0].status == Status.UNCHANGED


def test_telemetry_dry_run_enabled_file_reports_would_create(tmp_path: Path):
    from settings_sync.codegraph import sync_codegraph_telemetry

    paths = _paths(tmp_path)
    target = paths.codegraph_dir / "telemetry.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"enabled": True}))
    outcomes = sync_codegraph_telemetry(paths, dry_run=True)
    assert outcomes[0].status == Status.WOULD_CREATE


def test_telemetry_real_run_invokes_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import sync_codegraph_telemetry

    paths = _paths(tmp_path)
    launcher = _install_fake_version(paths)
    calls = []

    def fake_run(argv, check, capture_output):
        calls.append(argv)
        assert check is True

    monkeypatch.setattr("settings_sync.codegraph.subprocess.run", fake_run)
    outcomes = sync_codegraph_telemetry(paths, dry_run=False)
    assert outcomes[0].status == Status.CREATED
    assert calls == [[str(launcher), "telemetry", "off"]]


def test_telemetry_real_run_requires_binary(tmp_path: Path):
    from settings_sync.codegraph import sync_codegraph_telemetry

    paths = _paths(tmp_path)
    with pytest.raises(ValueError, match="installed binary"):
        sync_codegraph_telemetry(paths, dry_run=False)


def test_telemetry_off_failure_becomes_valueerror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import subprocess as subprocess_module
    from settings_sync.codegraph import sync_codegraph_telemetry

    paths = _paths(tmp_path)
    _install_fake_version(paths)

    def failing_run(argv, check, capture_output):
        raise subprocess_module.CalledProcessError(1, argv)

    monkeypatch.setattr("settings_sync.codegraph.subprocess.run", failing_run)
    with pytest.raises(ValueError, match="codegraph telemetry off failed"):
        sync_codegraph_telemetry(paths, dry_run=False)
