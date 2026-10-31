from pathlib import Path
import json
import os
import shutil

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(home / ".local" / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    for key in ("AGENT_CONFIG_REPO", "CODEX_HOME", "OPENCODE_CONFIG_DIR", "PI_CODING_AGENT_DIR", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(key, raising=False)
    # Model a machine with ~/.local/bin on PATH so the codegraph launcher's
    # off-PATH classification does not fire on freshly-installed stubs.
    (home / ".local" / "bin").mkdir(parents=True)
    monkeypatch.setenv("PATH", str(home / ".local" / "bin") + os.pathsep + os.environ["PATH"])
    return home


@pytest.fixture
def source_home(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "rules").mkdir(parents=True, exist_ok=True)
    (source / "rules/global.md").write_text("# Rules\nSee @skills/uv.\n")
    for name in ("harnesses/opencode", "harnesses/pi", "harnesses/goose", "harnesses/gemini", "harnesses/codex", "harnesses/no-mistakes", "harnesses/claude", "commands", "agents", "skills", "hooks", "custom"):
        (source / name).mkdir(parents=True)
    for name, filename in (("harnesses/opencode", "opencode.json"), ("harnesses/opencode", "tui.json"), ("harnesses/pi", "settings.json"), ("harnesses/gemini", "settings.json"), ("harnesses/claude", "settings.json")):
        (source / name / filename).write_text(json.dumps({"model": "shared"}))
    (source / "harnesses/goose" / "config.yaml").write_text("GOOSE_TELEMETRY_ENABLED: false\n")
    (source / "harnesses/goose" / "custom_providers").mkdir()
    (source / "harnesses/no-mistakes" / "config.yaml").write_text("{}\n")
    (source / "harnesses/pi" / "mcp.json").write_text(json.dumps({
        "mcpServers": {"codegraph": {"command": "codegraph", "args": ["serve", "--mcp"], "exposure": "direct"}}
    }))
    (source / "harnesses/codex" / "config.toml").write_text('model = "shared"\n')
    (source / "harnesses/opencode/plugins").mkdir()
    install_hook_sources(source)
    return source


def install_hook_sources(source: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    shutil.copytree(repo / "hooks", source / "hooks", dirs_exist_ok=True)
    for harness in ("codex", "goose", "gemini"):
        (source / "harnesses" / harness).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / "harnesses" / harness / "hooks.json", source / "harnesses" / harness / "hooks.json")


@pytest.fixture(autouse=True)
def stub_codegraph_download(monkeypatch: pytest.MonkeyPatch):
    """No test downloads a release tarball: fake download_and_extract writes a
    stub launcher. Tests that need different fakes re-patch inside the test
    body, which runs after this fixture and wins."""
    def fake(url: str, version_dir: Path) -> None:
        launcher = version_dir / "bin" / "codegraph"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text("#!/bin/sh\necho 1.6.2\n")
        launcher.chmod(0o755)
    monkeypatch.setattr("settings_sync.codegraph.download_and_extract", fake)
