import json
import pathlib

import pytest
from typer.testing import CliRunner

from settings_sync.cli import app
from settings_sync.pi import sync_pi_config, sync_pi_context, sync_pi_keybindings
from settings_sync.sync import Status


@pytest.fixture
def pi_template(tmp_path: pathlib.Path) -> pathlib.Path:
    """A pointer template at <claude>/pi/settings.json."""
    template = tmp_path / "claude" / "pi" / "settings.json"
    template.parent.mkdir(parents=True)
    template.write_text(json.dumps({"skills": ["~/.claude/skills"], "prompts": ["~/.claude/commands"]}))
    return template


@pytest.fixture
def pi_keybindings(tmp_path: pathlib.Path) -> pathlib.Path:
    """A keybindings source at <claude>/pi/keybindings.json."""
    source = tmp_path / "claude" / "pi" / "keybindings.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"app.tree.foldOrUp": ["alt+left"], "app.tree.unfoldOrDown": ["alt+right"]}))
    return source


@pytest.fixture
def claude_md(tmp_path: pathlib.Path) -> pathlib.Path:
    """A CLAUDE.md with an @skills/ reference."""
    claude_md = tmp_path / "claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True)
    claude_md.write_text("# Rules\nExtra rules.\nSee @skills/uv.\n")
    return claude_md


@pytest.fixture
def pi_home(tmp_path: pathlib.Path) -> pathlib.Path:
    """A full ~/.claude home with pi template, CLAUDE.md, and a skill."""
    home = tmp_path / "claude"
    (home / "harnesses/pi").mkdir(parents=True)
    (home / "harnesses/pi" / "settings.json").write_text(json.dumps({"skills": ["~/.claude/skills"]}))
    (home / "harnesses/pi" / "keybindings.json").write_text(json.dumps({"app.tree.foldOrUp": ["alt+left"], "app.tree.unfoldOrDown": ["alt+right"]}))
    (home / "rules").mkdir(parents=True, exist_ok=True)
    (home / "rules/global.md").write_text("# Rules\nExtra rules.\nSee @skills/uv.\n")
    (home / "skills").mkdir(parents=True)
    (home / "skills" / "uv").mkdir(parents=True)
    (home / "skills" / "uv" / "SKILL.md").write_text("---\nname: uv\ndescription: d\n---\nBody.\n")
    (home / "commands").mkdir()
    return home


runner = CliRunner()


# ---- sync_pi_config (wholesale copy; template is single source of truth) ----


def test_pi_config_creates_from_template(tmp_path: pathlib.Path, pi_template: pathlib.Path):
    target = tmp_path / "agent" / "settings.json"

    outcome = sync_pi_config(target, pi_template)

    assert outcome.status == Status.CREATED
    assert json.loads(target.read_text())["skills"] == ["~/.claude/skills"]


def test_pi_config_retains_native_state(tmp_path: pathlib.Path, pi_template: pathlib.Path):
    target = tmp_path / "agent" / "settings.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"lastChangelogVersion": "0.80.6"}))

    outcome = sync_pi_config(target, pi_template)

    assert outcome.status == Status.REPLACED
    assert json.loads(target.read_text()) == {"skills": ["~/.claude/skills"], "prompts": ["~/.claude/commands"], "lastChangelogVersion": "0.80.6"}


def test_pi_config_unchanged_when_identical(tmp_path: pathlib.Path, pi_template: pathlib.Path):
    target = tmp_path / "agent" / "settings.json"
    target.parent.mkdir(parents=True)
    target.write_text(pi_template.read_text())

    outcome = sync_pi_config(target, pi_template)

    assert outcome.status == Status.UNCHANGED


@pytest.mark.parametrize("dry_status", [(True, Status.WOULD_CREATE), (False, Status.CREATED)])
def test_pi_config_dry_run_creates_nothing(tmp_path: pathlib.Path, pi_template: pathlib.Path, dry_status: tuple[bool, Status]):
    dry_run, expected = dry_status
    target = tmp_path / "agent" / "settings.json"

    outcome = sync_pi_config(target, pi_template, dry_run=dry_run)

    assert outcome.status == expected
    assert (not target.exists()) if dry_run else target.exists()


def test_pi_config_dry_run_reports_would_replace_when_diverging(tmp_path: pathlib.Path, pi_template: pathlib.Path):
    target = tmp_path / "agent" / "settings.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"lastChangelogVersion": "0.80.6"}))

    outcome = sync_pi_config(target, pi_template, dry_run=True)

    assert outcome.status == Status.WOULD_REPLACE
    assert json.loads(target.read_text()) == {"lastChangelogVersion": "0.80.6"}


def test_pi_config_no_source_when_template_missing(tmp_path: pathlib.Path):
    outcome = sync_pi_config(tmp_path / "agent" / "settings.json", tmp_path / "missing" / "settings.json")

    assert outcome.status == Status.NO_SOURCE


# ---- sync_pi_keybindings (wholesale copy; source is single source of truth) ----


def test_pi_keybindings_creates_from_source(tmp_path: pathlib.Path, pi_keybindings: pathlib.Path):
    target = tmp_path / "agent" / "keybindings.json"

    outcome = sync_pi_keybindings(target, pi_keybindings)

    assert outcome.status == Status.CREATED
    assert json.loads(target.read_text())["app.tree.foldOrUp"] == ["alt+left"]


def test_pi_keybindings_preserves_local_edits(tmp_path: pathlib.Path, pi_keybindings: pathlib.Path):
    target = tmp_path / "agent" / "keybindings.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"hand": "edited"}))

    outcome = sync_pi_keybindings(target, pi_keybindings)

    assert outcome.status == Status.SKIPPED
    assert json.loads(target.read_text()) == {"hand": "edited"}


def test_pi_keybindings_unchanged_when_identical(tmp_path: pathlib.Path, pi_keybindings: pathlib.Path):
    target = tmp_path / "agent" / "keybindings.json"
    target.parent.mkdir(parents=True)
    target.write_text(pi_keybindings.read_text())

    outcome = sync_pi_keybindings(target, pi_keybindings)

    assert outcome.status == Status.UNCHANGED


@pytest.mark.parametrize("dry_status", [(True, Status.WOULD_CREATE), (False, Status.CREATED)])
def test_pi_keybindings_dry_run_creates_nothing(tmp_path: pathlib.Path, pi_keybindings: pathlib.Path, dry_status: tuple[bool, Status]):
    dry_run, expected = dry_status
    target = tmp_path / "agent" / "keybindings.json"

    outcome = sync_pi_keybindings(target, pi_keybindings, dry_run=dry_run)

    assert outcome.status == expected
    assert (not target.exists()) if dry_run else target.exists()


def test_pi_keybindings_no_source_when_missing(tmp_path: pathlib.Path):
    outcome = sync_pi_keybindings(tmp_path / "agent" / "keybindings.json", tmp_path / "missing" / "keybindings.json")

    assert outcome.status == Status.NO_SOURCE


# ---- sync_pi_context (inlined CLAUDE.md; refuse-to-clobber without --force) ----


def test_pi_context_creates_inlined(tmp_path: pathlib.Path, claude_md: pathlib.Path):
    target = tmp_path / "agent" / "CLAUDE.md"

    outcome = sync_pi_context(target, claude_md)

    assert outcome.status == Status.CREATED
    written = target.read_text()
    assert "Extra rules." in written
    assert "the `uv` skill" in written
    assert "@skills/uv" not in written


def test_pi_context_unchanged_when_identical(tmp_path: pathlib.Path, claude_md: pathlib.Path):
    target = tmp_path / "agent" / "CLAUDE.md"
    target.parent.mkdir(parents=True)
    sync_pi_context(target, claude_md)

    outcome = sync_pi_context(target, claude_md)

    assert outcome.status == Status.UNCHANGED


def test_pi_context_skips_diverging_without_force(tmp_path: pathlib.Path, claude_md: pathlib.Path):
    target = tmp_path / "agent" / "CLAUDE.md"
    target.parent.mkdir(parents=True)
    target.write_text("hand-edited context\n")

    outcome = sync_pi_context(target, claude_md)

    assert outcome.status == Status.SKIPPED
    assert target.read_text() == "hand-edited context\n"


def test_pi_context_force_overwrites_diverging(tmp_path: pathlib.Path, claude_md: pathlib.Path):
    target = tmp_path / "agent" / "CLAUDE.md"
    target.parent.mkdir(parents=True)
    target.write_text("hand-edited context\n")

    outcome = sync_pi_context(target, claude_md, force=True)

    assert outcome.status == Status.REPLACED
    assert "# Rules" in target.read_text()


def test_pi_context_no_source_when_claude_md_missing(tmp_path: pathlib.Path):
    outcome = sync_pi_context(tmp_path / "agent" / "CLAUDE.md", tmp_path / "missing" / "CLAUDE.md")

    assert outcome.status == Status.NO_SOURCE


# ---- CLI: sync pi ----


def test_cli_pi_config_creates_settings(tmp_path: pathlib.Path, pi_home: pathlib.Path):
    pi_dir = tmp_path / "pi-agent"

    result = runner.invoke(app, ["--claude-dir", str(pi_home), "--pi-dir", str(pi_dir), "pi", "config"])

    assert result.exit_code == 0
    assert json.loads((pi_dir / "settings.json").read_text())["skills"] == ["~/.claude/skills"]


def test_cli_pi_context_creates_inlined_claude_md(tmp_path: pathlib.Path, pi_home: pathlib.Path):
    pi_dir = tmp_path / "pi-agent"

    result = runner.invoke(app, ["--claude-dir", str(pi_home), "--pi-dir", str(pi_dir), "pi", "context"])

    assert result.exit_code == 0
    written = (pi_dir / "CLAUDE.md").read_text()
    assert "Extra rules." in written
    assert "the `uv` skill" in written


def test_cli_pi_bare_runs_config_and_context(tmp_path: pathlib.Path, pi_home: pathlib.Path):
    pi_dir = tmp_path / "pi-agent"

    result = runner.invoke(app, ["--claude-dir", str(pi_home), "--pi-dir", str(pi_dir), "pi"])

    assert result.exit_code == 0
    assert (pi_dir / "settings.json").is_file()
    assert (pi_dir / "CLAUDE.md").is_file()


def test_cli_pi_config_check_detects_drift(tmp_path: pathlib.Path, pi_home: pathlib.Path):
    pi_dir = tmp_path / "pi-agent"
    pi_dir.mkdir(parents=True)
    (pi_dir / "settings.json").write_text(json.dumps({"hand": "edited"}))

    result = runner.invoke(app, ["--check", "--claude-dir", str(pi_home), "--pi-dir", str(pi_dir), "pi", "config"])

    assert result.exit_code != 0
    assert json.loads((pi_dir / "settings.json").read_text()) == {"hand": "edited"}


def test_cli_pi_keybindings_creates(tmp_path: pathlib.Path, pi_home: pathlib.Path):
    pi_dir = tmp_path / "pi-agent"

    result = runner.invoke(app, ["--claude-dir", str(pi_home), "--pi-dir", str(pi_dir), "pi", "keybindings"])

    assert result.exit_code == 0
    assert json.loads((pi_dir / "keybindings.json").read_text())["app.tree.foldOrUp"] == ["alt+left"]


def test_cli_pi_bare_writes_keybindings(tmp_path: pathlib.Path, pi_home: pathlib.Path):
    pi_dir = tmp_path / "pi-agent"

    result = runner.invoke(app, ["--claude-dir", str(pi_home), "--pi-dir", str(pi_dir), "pi"])

    assert result.exit_code == 0
    assert (pi_dir / "keybindings.json").is_file()
    assert json.loads((pi_dir / "keybindings.json").read_text())["app.tree.unfoldOrDown"] == ["alt+right"]
