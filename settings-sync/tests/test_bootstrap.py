import json
import os
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/bootstrap.sh"


@pytest.fixture
def installer_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    monkeypatch.setenv("PATH", str(binaries) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("INSTALL_LOG", str(tmp_path / "install.log"))
    for name in ("pi", "npm"):
        executable = binaries / name
        executable.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$INSTALL_LOG"\nexit "${INSTALL_FAIL:-0}"\n')
        executable.chmod(0o755)
    return binaries


def test_matching_pin_skips_and_changed_pin_installs(source_home: Path, isolated_home: Path, installer_env: Path, tmp_path: Path):
    template = source_home / "harnesses/pi/settings.json"
    template.write_text(json.dumps({"packages": ["npm:example@1.0.0"]}))
    package = isolated_home / ".pi/agent/npm/node_modules/example/package.json"
    package.parent.mkdir(parents=True)
    package.write_text('{"version":"1.0.0"}')
    log = tmp_path / "install.log"
    result = subprocess.run(["bash", str(SCRIPT), str(source_home), "pi"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not log.exists()
    template.write_text(json.dumps({"packages": ["npm:example@2.0.0"]}))
    # Fake installer exits successfully but leaves disk at old version: must fail verification.
    result = subprocess.run(["bash", str(SCRIPT), str(source_home), "pi"], capture_output=True, text=True)
    assert result.returncode == 1
    assert "install npm:example@2.0.0" in log.read_text()


def test_failed_installer_propagates(source_home: Path, installer_env: Path, monkeypatch: pytest.MonkeyPatch):
    (source_home / "harnesses/pi/settings.json").write_text('{"packages":["npm:example@1.0.0"]}')
    monkeypatch.setenv("INSTALL_FAIL", "7")
    result = subprocess.run(["bash", str(SCRIPT), str(source_home), "pi"], capture_output=True, text=True)
    assert result.returncode == 1
    assert "failed" in result.stderr


def test_opencode_bundle_keeps_preexisting_skills(source_home: Path, isolated_home: Path, installer_env: Path, tmp_path: Path):
    tools = tmp_path / "tools"
    bundle = tools / "evo-hq-cli/lib/python3.13/site-packages/evo/opencode_plugin/evo.bundle.js"
    bundle.parent.mkdir(parents=True)
    bundle.write_text("pinned bundle")
    for name, output in (("opencode", ""), ("uv", str(tools)), ("evo", "evo-hq-cli 0.8.0")):
        script = installer_env / name
        script.write_text(f"#!/bin/sh\nprintf '%s\\n' '{output}'\n")
        script.chmod(0o755)
    (installer_env / "uv").write_text(f"""#!/bin/sh
case "$*" in
  'tool list') echo 'evo-hq-cli v0.8.0';;
  'tool dir') echo '{tools}';;
esac
""")
    skill = isolated_home / ".agents/skills/discover/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("Personal skill")
    result = subprocess.run(["bash", str(SCRIPT), str(source_home), "opencode"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert skill.read_text() == "Personal skill"
    assert (isolated_home / ".config/opencode/plugins/evo.js").read_text() == "pinned bundle"


@pytest.mark.parametrize("flag", ["--dry-run", "--check"])
def test_global_preview_prevents_bootstrap(source_home: Path, isolated_home: Path, flag: str):
    from typer.testing import CliRunner
    from settings_sync.cli import agent_config_app
    from tests.test_read_only import snapshot
    script = source_home / "scripts/bootstrap.sh"
    script.parent.mkdir()
    marker = source_home / "installer-ran"
    script.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    before = snapshot(isolated_home)
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), flag, "bootstrap", "pi"])
    assert result.exit_code == 0, result.output
    assert not marker.exists()
    assert snapshot(isolated_home) == before


def test_bootstrap_passes_effective_destinations(source_home: Path, isolated_home: Path, tmp_path: Path):
    from typer.testing import CliRunner
    from settings_sync.cli import agent_config_app
    script = source_home / "scripts/bootstrap.sh"
    script.parent.mkdir()
    script.write_text('#!/bin/sh\nprintf "%s\\n" "$OPENCODE_CONFIG_DIR" "$AGENT_CONFIG_PI_HOME" > "$1/targets"\n')
    target = tmp_path / "custom pi"
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "--pi-dir", str(target), "bootstrap", "pi"])
    assert result.exit_code == 0, result.output
    assert (target / "settings.json").is_file()
    assert (source_home / "targets").read_text().splitlines() == [str(isolated_home / ".config/opencode"), str(target)]
    assert not (isolated_home / ".pi").exists()
