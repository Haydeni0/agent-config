import json
import platform
from pathlib import Path

import pytest

from settings_sync.codegraph import (
    CODEGRAPH_VERSION,
    current_platform,
    plan_codegraph_binary,
    release_url,
)
from settings_sync.registry import HARNESSES
from settings_sync.paths import Paths, resolve_paths
from settings_sync.cli import agent_config_app
from typer.testing import CliRunner
from settings_sync.actions import Status
from settings_sync.executor import Mode, execute
from settings_sync.ownership import OwnershipStore


def _paths(tmp_path: Path, **overrides) -> Paths:
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    return resolve_paths(HARNESSES, claude_dir=source, codegraph_dir=tmp_path / "cg", **overrides)


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


def _apply(plan, paths: Paths, mode: Mode):
    store = OwnershipStore()
    store.load(mode)
    return execute(plan(paths), mode, store)


def apply_binary(paths: Paths, mode: Mode):
    return _apply(plan_codegraph_binary, paths, mode)


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
    outcomes = apply_binary(paths, Mode.DRY_RUN)
    assert any(o.status == Status.WOULD_CREATE for o in outcomes)
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
    assert all(o.status == Status.UNCHANGED for o in apply_binary(paths, Mode.DRY_RUN))


def test_binary_dry_run_stale_symlink_reports_would_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    home = _fake_home(tmp_path, monkeypatch)
    paths = _paths(tmp_path)
    old = _install_fake_version(paths, "v0.9.0")
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "codegraph").symlink_to(old)
    assert any(o.status == Status.WOULD_REPLACE for o in apply_binary(paths, Mode.DRY_RUN))


def test_binary_dry_run_off_path_reports_warned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    home = _fake_home(tmp_path, monkeypatch)
    paths = _paths(tmp_path)
    launcher = _install_fake_version(paths)
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "codegraph").symlink_to(launcher)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert any(o.status == Status.WARNED for o in apply_binary(paths, Mode.DRY_RUN))


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
    assert any(o.status == Status.WARNED for o in apply_binary(paths, Mode.DRY_RUN))


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
    outcomes = apply_binary(paths, Mode.APPLY)
    assert any(o.status == Status.CREATED for o in outcomes)
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
    outcomes = apply_binary(paths, Mode.APPLY)
    assert all(o.status in (Status.UNCHANGED, Status.CREATED) for o in outcomes)
    assert any(o.status == Status.CREATED and "prune" in o.detail for o in outcomes)
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
    outcomes = apply_binary(paths, Mode.APPLY)
    assert all(o.status not in (Status.WARNED, Status.WOULD_CREATE, Status.WOULD_REPLACE) for o in outcomes)


def test_check_codegraph_never_downloads(source_home: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch):
    """S53: check previews would_create; the download stub fails the test if called."""
    def fail_download(url: str, version_dir: Path) -> None:
        raise AssertionError("download must not run in check")

    monkeypatch.setattr("settings_sync.codegraph.download_and_extract", fail_download)
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "check", "codegraph"])
    assert result.exit_code == 1, result.output
    assert "would_create" in result.output
    assert not (isolated_home / ".codegraph").exists()


def test_sync_codegraph_runs_telemetry_after_binary(source_home: Path, isolated_home: Path):
    """S64: telemetry succeeds in the same run using the launcher binary installed (D15)."""
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "codegraph"])
    assert result.exit_code == 0, result.output
    assert (isolated_home / ".codegraph" / "telemetry.json").is_file()
    assert json.loads((isolated_home / ".codegraph" / "telemetry.json").read_text())["enabled"] is False


def test_telemetry_failure_is_one_failed_outcome(source_home: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch):
    """S65: a nonzero telemetry exit fails that action only; binary and claude-mcp still land."""
    def failing_download(url: str, version_dir: Path) -> None:
        launcher = version_dir / "bin" / "codegraph"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text('#!/bin/sh\nif [ "$1" = "telemetry" ]; then exit 1; fi\nexit 0\n')
        launcher.chmod(0o755)

    monkeypatch.setattr("settings_sync.codegraph.download_and_extract", failing_download)
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "codegraph"])
    assert result.exit_code == 1, result.output
    assert "failed" in result.output
    assert (isolated_home / ".local" / "bin" / "codegraph").is_symlink()
    assert (isolated_home / ".claude.json").is_file()


def test_claude_mcp_written_with_and_without_profile_dir(source_home: Path, isolated_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """S49: --claude-home X writes X/../.claude.json; CLAUDE_CONFIG_DIR=P writes P/.claude.json."""
    runner = CliRunner()
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    custom = tmp_path / "custom-claude"
    result = runner.invoke(agent_config_app, ["--source", str(source_home), "--claude-home", str(custom), "sync", "codegraph", "claude-mcp"])
    assert result.exit_code == 0, result.output
    assert json.loads((custom.parent / ".claude.json").read_text())["mcpServers"]["codegraph"]["command"] == "codegraph"
    profile = tmp_path / "profile"
    result = runner.invoke(agent_config_app, ["--source", str(source_home), "--claude-home", str(profile), "sync", "codegraph", "claude-mcp"], env={"CLAUDE_CONFIG_DIR": str(profile)})
    assert result.exit_code == 0, result.output
    assert json.loads((profile / ".claude.json").read_text())["mcpServers"]["codegraph"]["command"] == "codegraph"


def test_claude_mcp_sets_entry_and_preserves_foreign_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import plan_claude_mcp

    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    paths = _paths(tmp_path)
    target = paths.claude_mcp_json
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "projects": {"/work": {"allowedTools": ["Bash"]}},
        "oauthAccount": {"email": "user@example.com"},
        "mcpServers": {"other": {"type": "stdio", "command": "other"}},
    }))
    outcomes = _apply(plan_claude_mcp, paths, Mode.APPLY)
    assert outcomes[0].status == Status.MERGED
    data = json.loads(target.read_text())
    assert data["mcpServers"]["codegraph"] == {
        "type": "stdio", "command": "codegraph", "args": ["serve", "--mcp"], "alwaysLoad": True,
    }
    assert data["projects"]["/work"]["allowedTools"] == ["Bash"]
    assert data["oauthAccount"] == {"email": "user@example.com"}
    assert data["mcpServers"]["other"]["command"] == "other"


def test_claude_mcp_idempotent_second_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import plan_claude_mcp

    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    paths = _paths(tmp_path)
    _apply(plan_claude_mcp, paths, Mode.APPLY)
    before = paths.claude_mcp_json.read_text()
    outcomes = _apply(plan_claude_mcp, paths, Mode.APPLY)
    assert outcomes[0].status == Status.UNCHANGED
    assert paths.claude_mcp_json.read_text() == before


def test_claude_mcp_creates_absent_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import plan_claude_mcp

    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    paths = _paths(tmp_path)
    outcomes = _apply(plan_claude_mcp, paths, Mode.APPLY)
    target = paths.claude_mcp_json
    assert target.is_file()
    assert json.loads(target.read_text())["mcpServers"]["codegraph"]["command"] == "codegraph"


def test_claude_mcp_refuses_unparseable_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import plan_claude_mcp

    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    paths = _paths(tmp_path)
    target = paths.claude_mcp_json
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{not json")
    outcomes = _apply(plan_claude_mcp, paths, Mode.APPLY)
    assert outcomes[0].status == Status.FAILED
    assert "could not merge configuration" in outcomes[0].detail
    assert target.read_text() == "{not json"


def _agy_paths(tmp_path: Path, **overrides) -> Paths:
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    return resolve_paths(HARNESSES, claude_dir=source, agy_dir=tmp_path / "gemini-config", codegraph_dir=tmp_path / "cg", **overrides)


def test_agy_mcp_uses_unified_path_when_migrated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import plan_agy_mcp

    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    paths = _agy_paths(tmp_path)
    paths.agy_dir.mkdir(parents=True)
    (paths.agy_dir / ".migrated").write_text("")
    _apply(plan_agy_mcp, paths, Mode.APPLY)
    target = paths.agy_dir / "mcp_config.json"
    assert target.is_file()
    entry = json.loads(target.read_text())["mcpServers"]["codegraph"]
    assert entry == {"command": "codegraph", "args": ["serve", "--mcp"]}
    assert "type" not in entry


def test_agy_mcp_uses_unified_path_when_file_exists_without_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import plan_agy_mcp

    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    paths = _agy_paths(tmp_path)
    paths.agy_dir.mkdir(parents=True)
    (paths.agy_dir / "mcp_config.json").write_text(json.dumps({"mcpServers": {"other": {"command": "other"}}}))
    _apply(plan_agy_mcp, paths, Mode.APPLY)
    data = json.loads((paths.agy_dir / "mcp_config.json").read_text())
    assert data["mcpServers"]["other"] == {"command": "other"}
    assert data["mcpServers"]["codegraph"]["command"] == "codegraph"


def test_agy_mcp_falls_back_to_legacy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import plan_agy_mcp

    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    paths = _agy_paths(tmp_path)
    paths.agy_dir.mkdir(parents=True)
    _apply(plan_agy_mcp, paths, Mode.APPLY)
    legacy = paths.agy_dir.parent / "antigravity" / "mcp_config.json"
    assert legacy.is_file()
    assert not (paths.agy_dir / "mcp_config.json").exists()


def test_agy_mcp_darwin_writes_absolute_launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import plan_agy_mcp

    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "darwin")
    paths = _agy_paths(tmp_path)
    paths.agy_dir.mkdir(parents=True)
    (paths.agy_dir / ".migrated").write_text("")
    launcher = paths.codegraph_dir / "versions" / CODEGRAPH_VERSION / "bin" / "codegraph"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("#!/bin/sh\n")
    _apply(plan_agy_mcp, paths, Mode.APPLY)
    entry = json.loads((paths.agy_dir / "mcp_config.json").read_text())["mcpServers"]["codegraph"]
    assert entry["command"] == str(launcher)
    assert entry["args"] == ["serve", "--mcp"]


def test_agy_mcp_darwin_missing_binary_uses_pinned_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import plan_agy_mcp

    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "darwin")
    paths = _agy_paths(tmp_path)
    paths.agy_dir.mkdir(parents=True)
    (paths.agy_dir / ".migrated").write_text("")
    _apply(plan_agy_mcp, paths, Mode.APPLY)
    entry = json.loads((paths.agy_dir / "mcp_config.json").read_text())["mcpServers"]["codegraph"]
    assert entry["command"] == str(paths.codegraph_dir / "versions" / CODEGRAPH_VERSION / "bin" / "codegraph")


def test_pi_mcp_merges_and_preserves_user_servers(tmp_path: Path):
    from settings_sync.codegraph import plan_pi_mcp

    (tmp_path / "source").mkdir()
    paths = resolve_paths(HARNESSES, claude_dir=tmp_path / "source", pi_dir=tmp_path / "pi", codegraph_dir=tmp_path / "cg")
    target = paths.pi_dir / "mcp.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"mcpServers": {"mine": {"command": "mine"}}}))
    template = paths.source_dir / "harnesses/pi/mcp.json"
    template.parent.mkdir(parents=True)
    template.write_text(json.dumps({
        "mcpServers": {"codegraph": {"command": "codegraph", "args": ["serve", "--mcp"], "exposure": "direct"}}
    }))
    _apply(plan_pi_mcp, paths, Mode.APPLY)
    data = json.loads(target.read_text())
    assert data["mcpServers"]["mine"] == {"command": "mine"}
    entry = data["mcpServers"]["codegraph"]
    assert entry == {"command": "codegraph", "args": ["serve", "--mcp"], "exposure": "direct"}
    assert "type" not in entry


def test_telemetry_dry_run_no_file_reports_would_create(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import plan_codegraph_telemetry

    paths = _paths(tmp_path)
    outcomes = _apply(plan_codegraph_telemetry, paths, Mode.DRY_RUN)
    assert outcomes[0].status == Status.WOULD_CREATE


def test_telemetry_dry_run_stored_optout_reports_unchanged(tmp_path: Path):
    from settings_sync.codegraph import plan_codegraph_telemetry

    paths = _paths(tmp_path)
    target = paths.codegraph_dir / "telemetry.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"enabled": False, "machine_id": None}))
    outcomes = _apply(plan_codegraph_telemetry, paths, Mode.DRY_RUN)
    assert outcomes[0].status == Status.UNCHANGED


def test_telemetry_dry_run_enabled_file_reports_would_create(tmp_path: Path):
    from settings_sync.codegraph import plan_codegraph_telemetry

    paths = _paths(tmp_path)
    target = paths.codegraph_dir / "telemetry.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"enabled": True}))
    outcomes = _apply(plan_codegraph_telemetry, paths, Mode.DRY_RUN)
    assert outcomes[0].status == Status.WOULD_CREATE


def test_telemetry_real_run_invokes_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.codegraph import plan_codegraph_telemetry

    paths = _paths(tmp_path)
    launcher = _install_fake_version(paths)
    calls = []

    def fake_run(argv, check, capture_output):
        calls.append(argv)
        assert check is True

    monkeypatch.setattr("settings_sync.codegraph.subprocess.run", fake_run)
    outcomes = _apply(plan_codegraph_telemetry, paths, Mode.APPLY)
    assert outcomes[0].status == Status.CREATED
    assert calls == [[str(launcher), "telemetry", "off"]]


def test_telemetry_real_run_requires_binary(tmp_path: Path):
    from settings_sync.codegraph import plan_codegraph_telemetry

    paths = _paths(tmp_path)
    outcome = _apply(plan_codegraph_telemetry, paths, Mode.APPLY)[0]
    assert outcome.status == Status.FAILED
    assert "installed binary" in outcome.detail


def test_telemetry_off_failure_becomes_valueerror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import subprocess as subprocess_module
    from settings_sync.codegraph import plan_codegraph_telemetry

    paths = _paths(tmp_path)
    _install_fake_version(paths)

    def failing_run(argv, check, capture_output):
        raise subprocess_module.CalledProcessError(1, argv)

    monkeypatch.setattr("settings_sync.codegraph.subprocess.run", failing_run)
    outcome = _apply(plan_codegraph_telemetry, paths, Mode.APPLY)[0]
    assert outcome.status == Status.FAILED
    assert "telemetry" in outcome.detail


def test_binary_failed_download_installs_no_dangling_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Finding 4: on a failed download the links are not installed dangling and
    the already-installed version survives the prune."""
    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    home = _fake_home(tmp_path, monkeypatch)
    paths = _paths(tmp_path)
    old = _install_fake_version(paths, "v0.9.0")

    def failing_download(url: str, version_dir: Path) -> None:
        raise ValueError("network down")

    monkeypatch.setattr("settings_sync.codegraph.download_and_extract", failing_download)
    outcomes = apply_binary(paths, Mode.APPLY)
    assert any(o.status == Status.FAILED for o in outcomes)
    assert not (paths.codegraph_dir / "versions" / CODEGRAPH_VERSION / "bin" / "codegraph").exists()
    assert not (paths.codegraph_dir / "current").exists()
    assert old.is_file()


def test_binary_prune_protects_targets_of_existing_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Finding 4: a version an installed (even unmanaged) link still points at
    is not pruned, so a skipped link flip never dangles."""
    monkeypatch.setattr("settings_sync.codegraph.current_platform", lambda: "linux")
    home = _fake_home(tmp_path, monkeypatch)
    paths = _paths(tmp_path)
    old = _install_fake_version(paths, "v0.9.0")
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "codegraph").symlink_to(old)
    (paths.codegraph_dir / "current").symlink_to(old.parent.parent)

    def fake_download(url: str, version_dir: Path) -> None:
        launcher = version_dir / "bin" / "codegraph"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text("#!/bin/sh\necho 1.6.2\n")
        launcher.chmod(0o755)

    monkeypatch.setattr("settings_sync.codegraph.download_and_extract", fake_download)
    outcomes = apply_binary(paths, Mode.APPLY)
    assert any(o.status == Status.SKIPPED for o in outcomes)
    assert old.is_file()
    assert (paths.codegraph_dir / "versions" / CODEGRAPH_VERSION / "bin" / "codegraph").is_file()
