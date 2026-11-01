"""CodeGraph delivery: pinned binary install plus per-harness MCP server entries.

Spec: .agents/work/2026-10-31-codegraph-integration/spec.md. The codegraph
installer is never run; sync owns every config surface. The launcher
classification runs only in the dry-run branch (steps cannot distinguish
--check from --dry-run); real sync reports CREATED/REPLACED/UNCHANGED only.
"""

import copy
import json
import platform
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from settings_sync.actions import Action, Effect, MergedConfig, Outcome, Probe, Report, Status, Symlink
from settings_sync.merging import JsonCodec
from settings_sync.paths import Paths

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


def _stale_versions(install_root: Path, keep: Path) -> list[Path]:
    versions = install_root / "versions"
    if not versions.is_dir():
        return []
    return [entry for entry in versions.iterdir() if entry != keep and entry.is_dir()]


def _prune_other_versions(install_root: Path, keep: Path) -> None:
    for entry in _stale_versions(install_root, keep):
        shutil.rmtree(entry, ignore_errors=True)


def agy_mcp_config_path(paths: Paths) -> Path:
    """Unified ~/.gemini/config/mcp_config.json when migrated (marker or file
    exists - Antigravity creates the file on first launch post-migration),
    else the legacy ~/.gemini/antigravity/mcp_config.json. The legacy path
    derives from agy_dir so --agy-dir provides test isolation."""
    unified = paths.agy_dir / "mcp_config.json"
    if (paths.agy_dir / ".migrated").exists() or unified.exists():
        return unified
    return paths.agy_dir.parent / "antigravity" / "mcp_config.json"




def plan_codegraph_binary(paths: Paths) -> list[Action]:
    install_root = paths.codegraph_dir
    version_dir = install_root / "versions" / CODEGRAPH_VERSION
    launcher = version_dir / "bin" / "codegraph"
    symlink = paths.local_bin / "codegraph"
    current = install_root / "current"
    actions: list[Action] = []
    if not (launcher.exists() and _symlink_points_at(symlink, launcher)):
        url = release_url()
        actions.append(Effect(symlink, True, f"install codegraph {CODEGRAPH_VERSION} from {url}",
                              lambda: download_and_extract(url, version_dir)))
        actions.append(Symlink(symlink, launcher))
        actions.append(Symlink(current, version_dir))
    if _stale_versions(install_root, version_dir):
        actions.append(Effect(install_root, True, "prune stale codegraph versions",
                              lambda: _prune_other_versions(install_root, version_dir)))
    actions.append(Probe(symlink, lambda: _classify_dry_run(launcher, symlink)))
    return actions


AGY_MCP_ENTRY: dict = {"mcpServers": {"codegraph": {"command": "codegraph", "args": ["serve", "--mcp"]}}}


def plan_claude_mcp(paths: Paths) -> list[Action]:
    return [MergedConfig(path=paths.claude_mcp_json, codec=JsonCodec(), keys=copy.deepcopy(CLAUDE_MCP_ENTRY))]


def plan_agy_mcp(paths: Paths) -> list[Action]:
    entry = copy.deepcopy(AGY_MCP_ENTRY)
    if current_platform() == "darwin":
        entry["mcpServers"]["codegraph"]["command"] = str(paths.codegraph_dir / "versions" / CODEGRAPH_VERSION / "bin" / "codegraph")
    return [MergedConfig(path=agy_mcp_config_path(paths), codec=JsonCodec(), keys=entry)]


def plan_pi_mcp(paths: Paths) -> list[Action]:
    content = (paths.source_dir / "harnesses/pi/mcp.json").read_text()
    return [MergedConfig(path=paths.pi_dir / "mcp.json", codec=JsonCodec(), keys=json.loads(content))]


def plan_codegraph_telemetry(paths: Paths) -> list[Action]:
    target = paths.codegraph_dir / "telemetry.json"
    if target.exists():
        try:
            enabled = json.loads(target.read_text()).get("enabled")
        except ValueError as exc:
            return [Report(target, Status.FAILED, f"could not parse telemetry config: {exc}")]
        if enabled is False:
            return [Report(target, Status.UNCHANGED, "telemetry opt-out stored")]
    launcher = paths.codegraph_dir / "versions" / CODEGRAPH_VERSION / "bin" / "codegraph"

    def run_off() -> None:
        if not launcher.exists():
            raise ValueError("telemetry opt-out requires the installed binary; run the binary step first")
        subprocess.run([str(launcher), "telemetry", "off"], check=True, capture_output=True)

    return [Effect(target, True, "store telemetry opt-out (codegraph telemetry off)", run_off)]
