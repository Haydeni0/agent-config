import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest
from typer.testing import CliRunner

from settings_sync.cli import agent_config_app


@pytest.mark.parametrize("override", ["HOME", "CODEX_HOME"])
def test_destination_uses_invocation_environment(tmp_path: Path, override: str):
    source = tmp_path / "source with spaces"
    source.mkdir()
    (source / "rules").mkdir(parents=True, exist_ok=True)
    (source / "rules/global.md").write_text("# Shared rules\n")
    imported_home = tmp_path / "imported-home"
    imported_home.mkdir()
    destination = tmp_path / "invoked-home"
    destination.mkdir()
    script = dedent("""\
        import os
        from typer.testing import CliRunner
        from settings_sync.cli import agent_config_app
        os.environ[os.environ['TEST_OVERRIDE']] = os.environ['TEST_DESTINATION']
        result = CliRunner().invoke(agent_config_app, ['--claude-dir', os.environ['TEST_SOURCE'], 'sync', 'codex', 'agents-md'])
        print(result.output)
        raise SystemExit(result.exit_code)
    """)
    result = subprocess.run([sys.executable, "-c", script], env={**os.environ, "HOME": str(imported_home), "TEST_OVERRIDE": override, "TEST_DESTINATION": str(destination), "TEST_SOURCE": str(source)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    output = destination / ".codex" / "AGENTS.md" if override == "HOME" else destination / "AGENTS.md"
    assert output.read_text().endswith("# Shared rules\n")
    assert not (imported_home / ".codex").exists()


@pytest.mark.parametrize("source_option", ["flag", "environment", "pointer"])
def test_source_selection(tmp_path: Path, isolated_home: Path, source_option: str):
    source = tmp_path / "source"
    source.mkdir()
    (source / "rules").mkdir(parents=True, exist_ok=True)
    (source / "rules/global.md").write_text("# Selected source\n")
    pointer = isolated_home / ".config" / "agent-config" / "config.toml"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(f'source = "{source if source_option == "pointer" else tmp_path / "unused-source"}"\n')
    script = dedent("""\
        import os
        from typer.testing import CliRunner
        from settings_sync.cli import agent_config_app
        mode = os.environ['TEST_MODE']
        args = ['sync', 'codex', 'agents-md']
        if mode == 'flag':
            args = ['--source', os.environ['TEST_SOURCE'], *args]
            os.environ['AGENT_CONFIG_REPO'] = '/missing-env-source'
        elif mode == 'environment':
            os.environ['AGENT_CONFIG_REPO'] = os.environ['TEST_SOURCE']
        result = CliRunner().invoke(agent_config_app, args)
        print(result.output)
        raise SystemExit(result.exit_code)
    """)
    result = subprocess.run([sys.executable, "-c", script], env={**os.environ, "TEST_MODE": source_option, "TEST_SOURCE": str(source)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (isolated_home / ".codex" / "AGENTS.md").read_text().endswith("# Selected source\n")


def test_explicit_destination_wins(tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "rules").mkdir(parents=True, exist_ok=True)
    (source / "rules/global.md").write_text("# Rules\n")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "unused"))
    target = tmp_path / "chosen"
    result = CliRunner().invoke(agent_config_app, ["--source", str(source), "--codex-dir", str(target), "sync", "codex", "agents-md"])
    assert result.exit_code == 0, result.output
    assert (target / "AGENTS.md").read_text().endswith("# Rules\n")
    assert not (tmp_path / "unused").exists()
    assert not (isolated_home / ".codex").exists()


def test_configured_missing_source_is_an_error(isolated_home: Path, monkeypatch: pytest.MonkeyPatch):
    fallback = isolated_home / ".claude"
    fallback.mkdir()
    (fallback / "CLAUDE.md").write_text("Wrong source\n")
    monkeypatch.setenv("AGENT_CONFIG_REPO", str(isolated_home / "missing"))
    result = CliRunner().invoke(agent_config_app, ["sync", "codex", "agents-md"])
    assert result.exit_code != 0
    assert "source directory does not exist" in result.output
    assert not (isolated_home / ".codex").exists()


def test_empty_xdg_uses_home_defaults(source_home: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "")
    monkeypatch.setenv("XDG_STATE_HOME", "")
    monkeypatch.chdir(isolated_home)
    result = CliRunner().invoke(agent_config_app, ["--source", str(source_home), "sync", "opencode", "agents-md"])
    assert result.exit_code == 0, result.output
    assert (isolated_home / ".config/opencode/AGENTS.md").is_file()
    assert (isolated_home / ".local/state/agent-config/managed.json").is_file()
    assert not (isolated_home / "agent-config").exists()


@pytest.mark.parametrize("explicit", [False, True])
def test_opencode_destination_precedence(source_home: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch, explicit: bool):
    native = isolated_home / "native"
    chosen = isolated_home / "explicit"
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(native))
    args = ["--source", str(source_home)]
    if explicit:
        args += ["--opencode-dir", str(chosen)]
    result = CliRunner().invoke(agent_config_app, [*args, "sync", "opencode", "agents-md"])
    assert result.exit_code == 0, result.output
    assert ((chosen if explicit else native) / "AGENTS.md").is_file()
    assert not (isolated_home / ".config/opencode").exists()


def test_resolve_paths_honors_claude_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.paths import resolve_paths
    source = tmp_path / "source"
    source.mkdir()
    profile = tmp_path / "profile"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(profile))
    paths = resolve_paths(claude_dir=source)
    assert paths.claude_home == profile.expanduser().absolute()


def test_resolve_paths_honors_pi_coding_agent_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.paths import resolve_paths
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "pi-home"
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(target))
    paths = resolve_paths(claude_dir=source)
    assert paths.pi_dir == target.expanduser().absolute()


def test_resolve_paths_codegraph_dir_flag_and_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings_sync.paths import resolve_paths
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    paths = resolve_paths(claude_dir=source, codegraph_dir=tmp_path / "cg")
    assert paths.codegraph_dir == tmp_path / "cg"
    paths = resolve_paths(claude_dir=source)
    assert paths.codegraph_dir == (tmp_path / "home" / ".codegraph").expanduser().absolute()
