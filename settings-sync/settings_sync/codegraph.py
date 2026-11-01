"""CodeGraph delivery: pinned binary install plus per-harness MCP server entries.

Spec: .agents/work/2026-10-31-codegraph-integration/spec.md. The codegraph
installer is never run; sync owns every config surface. The launcher
classification runs only in the dry-run branch (steps cannot distinguish
--check from --dry-run); real sync reports CREATED/REPLACED/UNCHANGED only.
"""

import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from settings_sync.merging import sync_json_defaults
from settings_sync.paths import Paths
from settings_sync.actions import Outcome, Status

CODEGRAPH_VERSION = "v1.6.2"
CODEGRAPH_REPO = "colbymchenry/codegraph"

CLAUDE_MCP_ENTRY = {
    "mcpServers": {
        "codegraph": {
            "type": "stdio",
            "command": "codegraph",
            "args": ["serve", "--mcp"],
            "alwaysLoad": True,
        }
    }
}


def current_platform() -> str:
    """Platform for release assets: 'linux' or 'darwin'. Test seam."""
    name = platform.system()
    known = {"Linux": "linux", "Darwin": "darwin"}
    if name not in known:
        raise ValueError(f"unsupported platform for codegraph: {name}")
    return known[name]


def release_url(version: str = CODEGRAPH_VERSION) -> str:
    machine = platform.machine()
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    if arch is None:
        raise ValueError(f"unsupported architecture for codegraph: {machine}")
    return f"https://github.com/{CODEGRAPH_REPO}/releases/download/{version}/codegraph-{current_platform()}-{arch}.tar.gz"


def download_and_extract(url: str, version_dir: Path) -> None:
    """Download the release tarball and extract it into version_dir, stripping
    the single top-level directory. Fails as ValueError with url and dest, no
    partial state outside the temp dir (run_harness converts ValueError to
    FAILED, but tar/subprocess errors would otherwise escape its catch)."""
    with tempfile.TemporaryDirectory() as tmp:
        tarball = Path(tmp) / "cg.tar.gz"
        try:
            subprocess.run(["curl", "-fsSL", url, "-o", str(tarball)], check=True)
            version_dir.mkdir(parents=True, exist_ok=True)
            with tarfile.open(tarball) as tar:
                for member in tar.getmembers():
                    parts = member.path.split("/", 1)
                    if len(parts) < 2 or not parts[1]:
                        continue
                    member.path = parts[1]
                    tar.extract(member, version_dir)
        except (subprocess.CalledProcessError, tarfile.TarError, OSError) as exc:
            raise ValueError(f"codegraph download failed: url={url} dest={version_dir}: {exc}") from exc


def sync_codegraph_binary(paths: Paths, dry_run: bool) -> list[Outcome]:
    install_root = paths.codegraph_dir
    version_dir = install_root / "versions" / CODEGRAPH_VERSION
    launcher = version_dir / "bin" / "codegraph"
    symlink = paths.local_bin / "codegraph"

    if dry_run:
        return [_classify_dry_run(launcher, symlink)]

    if launcher.exists() and _symlink_points_at(symlink, launcher):
        _prune_other_versions(install_root, version_dir)
        return [Outcome(symlink, Status.UNCHANGED, f"codegraph {CODEGRAPH_VERSION} installed")]

    url = release_url()
    was_installed = symlink.exists() or symlink.is_symlink()
    download_and_extract(url, version_dir)
    symlink.parent.mkdir(parents=True, exist_ok=True)
    if symlink.exists() or symlink.is_symlink():
        symlink.unlink()
    symlink.symlink_to(launcher)
    current = install_root / "current"
    if current.is_symlink() or current.exists():
        current.unlink()
    current.symlink_to(version_dir)
    _prune_other_versions(install_root, version_dir)
    status = Status.REPLACED if was_installed else Status.CREATED
    return [Outcome(symlink, status, f"codegraph {CODEGRAPH_VERSION} installed from {url}")]


def _classify_dry_run(launcher: Path, symlink: Path) -> Outcome:
    if launcher.exists() and _symlink_points_at(symlink, launcher):
        which = shutil.which("codegraph")
        if which is None:
            return Outcome(symlink, Status.WARNED, f"codegraph installed at {symlink} but its directory is not on PATH")
        if Path(which).resolve() != symlink.resolve():
            return Outcome(symlink, Status.WARNED, f"a different codegraph resolves first on PATH: {which}")
        return Outcome(symlink, Status.UNCHANGED, f"codegraph {CODEGRAPH_VERSION} installed")
    if symlink.is_symlink() or symlink.exists():
        return Outcome(symlink, Status.WOULD_REPLACE, f"would reinstall codegraph {CODEGRAPH_VERSION} (launcher points elsewhere)")
    return Outcome(symlink, Status.WOULD_CREATE, f"would install codegraph {CODEGRAPH_VERSION} from {release_url()}")


def _symlink_points_at(symlink: Path, launcher: Path) -> bool:
    return symlink.is_symlink() and symlink.resolve() == launcher.resolve()


def _prune_other_versions(install_root: Path, keep: Path) -> None:
    versions = install_root / "versions"
    if not versions.is_dir():
        return
    for entry in versions.iterdir():
        if entry != keep and entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)


def sync_claude_mcp(paths: Paths, dry_run: bool) -> list[Outcome]:
    """Keyed-merge the MCP server entry into ~/.claude.json (or the profile
    copy). Only the mcpServers.codegraph key is managed; trust, oauth, and
    onboarding state pass through untouched (merge_defaults)."""
    target = paths.claude_mcp_json
    content = json.dumps(CLAUDE_MCP_ENTRY, indent=2)
    return [sync_json_defaults(target, content, dry_run)]


def agy_mcp_config_path(paths: Paths) -> Path:
    """Unified ~/.gemini/config/mcp_config.json when migrated (marker or file
    exists - Antigravity creates the file on first launch post-migration),
    else the legacy ~/.gemini/antigravity/mcp_config.json. The legacy path
    derives from agy_dir so --agy-dir provides test isolation."""
    unified = paths.agy_dir / "mcp_config.json"
    if (paths.agy_dir / ".migrated").exists() or unified.exists():
        return unified
    return paths.agy_dir.parent / "antigravity" / "mcp_config.json"


def sync_agy_mcp(paths: Paths, dry_run: bool) -> list[Outcome]:
    """Keyed-merge the Antigravity MCP entry. No 'type' field - Antigravity
    rejects type: "stdio" entries. On darwin the command is the absolute
    launcher path (GUI launches get a stripped PATH); the pinned path is
    computable without the binary, so it serves as the fallback."""
    command: str = "codegraph"
    if current_platform() == "darwin":
        command = str(paths.codegraph_dir / "versions" / CODEGRAPH_VERSION / "bin" / "codegraph")
    entry = {"mcpServers": {"codegraph": {"command": command, "args": ["serve", "--mcp"]}}}
    target = agy_mcp_config_path(paths)
    return [sync_json_defaults(target, json.dumps(entry, indent=2), dry_run)]


def sync_pi_mcp(paths: Paths, dry_run: bool) -> list[Outcome]:
    """Keyed-merge pi's mcp.json from the harnesses/pi/mcp.json template.
    exposure: "direct" is required - pi's default codemode never declares a
    server's tools to the model. Keyed merge (not wholesale) so user servers
    in the same file survive."""
    target = paths.pi_dir / "mcp.json"
    content = (paths.source_dir / "harnesses/pi/mcp.json").read_text()
    return [sync_json_defaults(target, content, dry_run)]


def sync_codegraph_telemetry(paths: Paths, dry_run: bool) -> list[Outcome]:
    """Store the anonymous-usage telemetry opt-out (codegraph defaults to on).
    The stored choice covers every process - CLI, MCP server, background
    daemon - and deletes any unsent queue; the spec leaves telemetry values
    at codegraph defaults but the user policy is opt-out everywhere, so sync
    enforces it on every machine it touches."""
    target = paths.codegraph_dir / "telemetry.json"
    enabled = None
    if target.exists():
        try:
            enabled = json.loads(target.read_text()).get("enabled")
        except ValueError as exc:
            return [Outcome(target, Status.FAILED, f"could not parse telemetry config: {exc}")]
    if enabled is False:
        return [Outcome(target, Status.UNCHANGED, "telemetry opt-out stored")]
    if dry_run:
        return [Outcome(target, Status.WOULD_CREATE, "would store telemetry opt-out")]
    launcher = paths.codegraph_dir / "versions" / CODEGRAPH_VERSION / "bin" / "codegraph"
    if not launcher.exists():
        raise ValueError("telemetry opt-out requires the installed binary; run the binary step first")
    try:
        subprocess.run([str(launcher), "telemetry", "off"], check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"codegraph telemetry off failed: returncode={exc.returncode}") from exc
    return [Outcome(target, Status.CREATED, "telemetry opt-out stored (codegraph telemetry off)")]
