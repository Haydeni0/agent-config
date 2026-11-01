import json
import pathlib

import pytest
from typer.testing import CliRunner

from settings_sync.actions import Mode, Status
from settings_sync.cli import agent_config_app
from settings_sync.executor import execute
from settings_sync.ownership import OwnershipStore
from settings_sync.paths import resolve_paths
from settings_sync.pi import plan_pi_config, plan_pi_keybindings


@pytest.fixture
def pi_template(tmp_path: pathlib.Path) -> pathlib.Path:
    """A pointer template at <claude>/pi/settings.json."""
    template = tmp_path / "claude" / "harnesses" / "pi" / "settings.json"
    template.parent.mkdir(parents=True)
    template.write_text(json.dumps({"skills": ["~/.claude/skills"], "prompts": ["~/.claude/commands"]}))
    return template


@pytest.fixture
def pi_keybindings(tmp_path: pathlib.Path) -> pathlib.Path:
    """A keybindings source at <claude>/pi/keybindings.json."""
    source = tmp_path / "claude" / "harnesses" / "pi" / "keybindings.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"app.tree.foldOrUp": ["alt+left"], "app.tree.unfoldOrDown": ["alt+right"]}))
    return source


@pytest.fixture
def pi_home(tmp_path: pathlib.Path) -> pathlib.Path:
    """A full ~/.claude home with pi template, CLAUDE.md, and a skill."""
    home = tmp_path / "claude"
    (home / "harnesses/pi").mkdir(parents=True)
    (home / "harnesses/pi" / "settings.json").write_text(json.dumps({"skills": ["~/.claude/skills"]}))
    (home / "harnesses/pi" / "mcp.json").write_text(json.dumps({"mcpServers": {"codegraph": {"command": "codegraph", "args": ["serve", "--mcp"], "exposure": "direct"}}}))
    (home / "harnesses/pi" / "keybindings.json").write_text(json.dumps({"app.tree.foldOrUp": ["alt+left"], "app.tree.unfoldOrDown": ["alt+right"]}))
    (home / "rules").mkdir(parents=True, exist_ok=True)
    (home / "rules/global.md").write_text("# Rules\nExtra rules.\nSee @skills/uv.\n")
    (home / "skills").mkdir(parents=True)
    (home / "skills" / "uv").mkdir(parents=True)
    (home / "skills" / "uv" / "SKILL.md").write_text("---\nname: uv\ndescription: d\n---\nBody.\n")
    (home / "commands").mkdir()
    return home




def _pi_paths(tmp_path: pathlib.Path):
    return resolve_paths(claude_dir=tmp_path / "claude", pi_dir=tmp_path / "agent")


def _apply(plan, paths, mode: Mode):
    store = OwnershipStore()
    store.load(mode)
    return execute(plan(paths), mode, store)


runner = CliRunner()


# ---- plan_pi_config ----


def test_pi_config_creates_from_template(tmp_path: pathlib.Path, pi_template: pathlib.Path):
    paths = _pi_paths(tmp_path)
    target = paths.pi_dir / "settings.json"

    outcome = _apply(plan_pi_config, paths, Mode.APPLY)[0]

    assert outcome.status == Status.MERGED
    assert json.loads(target.read_text())["skills"] == ["~/.claude/skills"]


def test_pi_config_retains_native_state(source_home: pathlib.Path, isolated_home: pathlib.Path):
    (source_home / "harnesses/pi/settings.json").write_text(json.dumps({"skills": ["~/.claude/skills"], "prompts": ["~/.claude/commands"]}))
    paths = resolve_paths(claude_dir=source_home, pi_dir=isolated_home / "pi", claude_home=isolated_home / ".claude")
    target = paths.pi_dir / "settings.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"lastChangelogVersion": "0.80.6"}))

    outcome = _apply(plan_pi_config, paths, Mode.APPLY)[0]

    assert outcome.status == Status.MERGED
    assert json.loads(target.read_text()) == {"skills": ["~/.claude/skills"], "prompts": ["~/.claude/commands"], "lastChangelogVersion": "0.80.6"}


def test_pi_config_unchanged_when_identical(tmp_path: pathlib.Path, pi_template: pathlib.Path):
    paths = _pi_paths(tmp_path)
    target = paths.pi_dir / "settings.json"
    target.parent.mkdir(parents=True)
    target.write_text(pi_template.read_text())

    outcome = _apply(plan_pi_config, paths, Mode.APPLY)[0]

    assert outcome.status == Status.UNCHANGED


@pytest.mark.parametrize("dry_status", [(True, Status.WOULD_CREATE), (False, Status.MERGED)])
def test_pi_config_dry_run_creates_nothing(tmp_path: pathlib.Path, pi_template: pathlib.Path, dry_status: tuple[bool, Status]):
    dry_run, expected = dry_status
    paths = _pi_paths(tmp_path)
    target = paths.pi_dir / "settings.json"

    outcome = _apply(plan_pi_config, paths, Mode.DRY_RUN if dry_run else Mode.APPLY)[0]

    assert outcome.status == expected
    assert (not target.exists()) if dry_run else target.exists()


def test_pi_config_dry_run_reports_would_merge_when_diverging(tmp_path: pathlib.Path, pi_template: pathlib.Path):
    paths = _pi_paths(tmp_path)
    target = paths.pi_dir / "settings.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"lastChangelogVersion": "0.80.6"}))

    outcome = _apply(plan_pi_config, paths, Mode.DRY_RUN)[0]

    assert outcome.status == Status.WOULD_MERGE
    assert json.loads(target.read_text()) == {"lastChangelogVersion": "0.80.6"}


def test_pi_config_no_source_when_template_missing(tmp_path: pathlib.Path):
    (tmp_path / "claude").mkdir(parents=True)
    paths = _pi_paths(tmp_path)

    with pytest.raises(OSError):
        plan_pi_config(paths)


# ---- plan_pi_keybindings ----


def test_pi_keybindings_creates_from_source(tmp_path: pathlib.Path, pi_keybindings: pathlib.Path):
    paths = _pi_paths(tmp_path)
    target = paths.pi_dir / "keybindings.json"

    outcome = _apply(plan_pi_keybindings, paths, Mode.APPLY)[0]

    assert outcome.status == Status.CREATED
    assert json.loads(target.read_text())["app.tree.foldOrUp"] == ["alt+left"]


def test_pi_keybindings_preserves_local_edits(tmp_path: pathlib.Path, pi_keybindings: pathlib.Path):
    paths = _pi_paths(tmp_path)
    target = paths.pi_dir / "keybindings.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"hand": "edited"}))

    outcome = _apply(plan_pi_keybindings, paths, Mode.APPLY)[0]

    assert outcome.status == Status.SKIPPED
    assert json.loads(target.read_text()) == {"hand": "edited"}


def test_pi_keybindings_unchanged_when_identical(tmp_path: pathlib.Path, pi_keybindings: pathlib.Path):
    paths = _pi_paths(tmp_path)
    target = paths.pi_dir / "keybindings.json"
    target.parent.mkdir(parents=True)
    target.write_text(pi_keybindings.read_text())

    outcome = _apply(plan_pi_keybindings, paths, Mode.APPLY)[0]

    assert outcome.status == Status.UNCHANGED


@pytest.mark.parametrize("dry_status", [(True, Status.WOULD_CREATE), (False, Status.CREATED)])
def test_pi_keybindings_dry_run_creates_nothing(tmp_path: pathlib.Path, pi_keybindings: pathlib.Path, dry_status: tuple[bool, Status]):
    dry_run, expected = dry_status
    paths = _pi_paths(tmp_path)
    target = paths.pi_dir / "keybindings.json"

    outcome = _apply(plan_pi_keybindings, paths, Mode.DRY_RUN if dry_run else Mode.APPLY)[0]

    assert outcome.status == expected
    assert (not target.exists()) if dry_run else target.exists()


def test_pi_keybindings_no_source_when_missing(tmp_path: pathlib.Path):
    (tmp_path / "claude").mkdir(parents=True)
    paths = _pi_paths(tmp_path)

    outcome = _apply(plan_pi_keybindings, paths, Mode.APPLY)[0]

    assert outcome.status == Status.NO_SOURCE


# ---- CLI: sync pi ----


def test_cli_pi_config_creates_settings(tmp_path: pathlib.Path, pi_home: pathlib.Path):
    pi_dir = tmp_path / "pi-agent"

    result = runner.invoke(agent_config_app, ["--claude-dir", str(pi_home), "--pi-dir", str(pi_dir), "sync", "pi", "config"])

    assert result.exit_code == 0
    assert json.loads((pi_dir / "settings.json").read_text())["skills"] == ["~/.claude/skills"]


def test_cli_pi_context_creates_inlined_claude_md(tmp_path: pathlib.Path, pi_home: pathlib.Path):
    pi_dir = tmp_path / "pi-agent"

    result = runner.invoke(agent_config_app, ["--claude-dir", str(pi_home), "--pi-dir", str(pi_dir), "sync", "pi", "context"])

    assert result.exit_code == 0
    written = (pi_dir / "CLAUDE.md").read_text()
    assert "Extra rules." in written
    assert "the `uv` skill" in written


def test_cli_pi_bare_runs_config_and_context(tmp_path: pathlib.Path, pi_home: pathlib.Path):
    pi_dir = tmp_path / "pi-agent"

    result = runner.invoke(agent_config_app, ["--claude-dir", str(pi_home), "--pi-dir", str(pi_dir), "sync", "pi"])

    assert result.exit_code == 0
    assert (pi_dir / "settings.json").is_file()
    assert (pi_dir / "CLAUDE.md").is_file()


def test_cli_pi_config_check_detects_drift(tmp_path: pathlib.Path, pi_home: pathlib.Path):
    pi_dir = tmp_path / "pi-agent"
    pi_dir.mkdir(parents=True)
    (pi_dir / "settings.json").write_text(json.dumps({"hand": "edited"}))

    result = runner.invoke(agent_config_app, ["--check", "--claude-dir", str(pi_home), "--pi-dir", str(pi_dir), "check", "pi", "config"])

    assert result.exit_code != 0
    assert json.loads((pi_dir / "settings.json").read_text()) == {"hand": "edited"}


def test_cli_pi_keybindings_creates(tmp_path: pathlib.Path, pi_home: pathlib.Path):
    pi_dir = tmp_path / "pi-agent"

    result = runner.invoke(agent_config_app, ["--claude-dir", str(pi_home), "--pi-dir", str(pi_dir), "sync", "pi", "keybindings"])

    assert result.exit_code == 0
    assert json.loads((pi_dir / "keybindings.json").read_text())["app.tree.foldOrUp"] == ["alt+left"]


def test_cli_pi_bare_writes_keybindings(tmp_path: pathlib.Path, pi_home: pathlib.Path):
    pi_dir = tmp_path / "pi-agent"

    result = runner.invoke(agent_config_app, ["--claude-dir", str(pi_home), "--pi-dir", str(pi_dir), "sync", "pi"])

    assert result.exit_code == 0
    assert (pi_dir / "keybindings.json").is_file()
    assert json.loads((pi_dir / "keybindings.json").read_text())["app.tree.unfoldOrDown"] == ["alt+right"]
