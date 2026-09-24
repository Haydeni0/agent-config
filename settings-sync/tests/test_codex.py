import pathlib

import pytest
from typer.testing import CliRunner

from settings_sync.cli import app
from settings_sync.codex import sync_codex_agents_md, sync_codex_config
from settings_sync.sync import Status

CONFIG_TEMPLATE = '[features]\nhooks = true\n'


@pytest.fixture
def codex_template(tmp_path: pathlib.Path) -> pathlib.Path:
    """A config template at <claude>/codex/config.toml."""
    template = tmp_path / "claude" / "codex" / "config.toml"
    template.parent.mkdir(parents=True)
    template.write_text(CONFIG_TEMPLATE)
    return template


@pytest.fixture
def claude_md(tmp_path: pathlib.Path) -> pathlib.Path:
    """A CLAUDE.md with an @skills/ reference."""
    claude_md = tmp_path / "claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True)
    claude_md.write_text("# Rules\nExtra rules.\nSee @skills/uv.\n")
    return claude_md


@pytest.fixture
def codex_home(tmp_path: pathlib.Path) -> pathlib.Path:
    """A full ~/.claude home with codex template, CLAUDE.md, and a skill."""
    home = tmp_path / "claude"
    (home / "codex").mkdir(parents=True)
    (home / "codex" / "config.toml").write_text(CONFIG_TEMPLATE)
    (home / "CLAUDE.md").write_text("# Rules\nExtra rules.\nSee @skills/uv.\n")
    (home / "skills").mkdir(parents=True)
    (home / "skills" / "uv").mkdir(parents=True)
    (home / "skills" / "uv" / "SKILL.md").write_text("---\nname: uv\ndescription: d\n---\nBody.\n")
    return home


runner = CliRunner()


# ---- sync_codex_config (managed defaults) ----


def test_codex_config_creates_from_template(tmp_path: pathlib.Path, codex_template: pathlib.Path):
    target = tmp_path / "codex" / "config.toml"

    outcome = sync_codex_config(target, codex_template)

    assert outcome.status == Status.CREATED
    assert target.read_text() == CONFIG_TEMPLATE


def test_codex_config_updates_managed_keys(tmp_path: pathlib.Path, codex_template: pathlib.Path):
    target = tmp_path / "codex" / "config.toml"
    target.parent.mkdir(parents=True)
    target.write_text('[features]\nhooks = false\n')

    outcome = sync_codex_config(target, codex_template)

    assert outcome.status == Status.REPLACED
    assert target.read_text() == CONFIG_TEMPLATE


def test_codex_config_dry_run_preserves_config(tmp_path: pathlib.Path, codex_template: pathlib.Path):
    target = tmp_path / "codex" / "config.toml"
    target.parent.mkdir(parents=True)
    target.write_text('[features]\nhooks = false\n')

    outcome = sync_codex_config(target, codex_template, dry_run=True)

    assert outcome.status == Status.WOULD_REPLACE
    assert target.read_text() == '[features]\nhooks = false\n'


def test_codex_config_unchanged_when_identical(tmp_path: pathlib.Path, codex_template: pathlib.Path):
    target = tmp_path / "codex" / "config.toml"
    target.parent.mkdir(parents=True)
    target.write_text(CONFIG_TEMPLATE)

    outcome = sync_codex_config(target, codex_template)

    assert outcome.status == Status.UNCHANGED


@pytest.mark.parametrize("dry_status", [(True, Status.WOULD_CREATE), (False, Status.CREATED)])
def test_codex_config_dry_run_creates_nothing(tmp_path: pathlib.Path, codex_template: pathlib.Path, dry_status: tuple[bool, Status]):
    dry_run, expected = dry_status
    target = tmp_path / "codex" / "config.toml"

    outcome = sync_codex_config(target, codex_template, dry_run=dry_run)

    assert outcome.status == expected
    assert (not target.exists()) if dry_run else target.exists()


def test_codex_config_no_source_when_template_missing(tmp_path: pathlib.Path):
    outcome = sync_codex_config(tmp_path / "codex" / "config.toml", tmp_path / "missing" / "config.toml")

    assert outcome.status == Status.NO_SOURCE


# ---- sync_codex_agents_md (inlined CLAUDE.md; refuse-to-clobber without --force) ----


def test_codex_agents_md_creates_inlined(tmp_path: pathlib.Path, claude_md: pathlib.Path):
    target = tmp_path / "codex" / "AGENTS.md"

    outcome = sync_codex_agents_md(target, claude_md)

    assert outcome.status == Status.CREATED
    written = target.read_text()
    assert "Extra rules." in written
    assert "the `uv` skill" in written
    assert "@skills/uv" not in written


def test_codex_agents_md_unchanged_when_identical(tmp_path: pathlib.Path, claude_md: pathlib.Path):
    target = tmp_path / "codex" / "AGENTS.md"
    target.parent.mkdir(parents=True)
    sync_codex_agents_md(target, claude_md)

    outcome = sync_codex_agents_md(target, claude_md)

    assert outcome.status == Status.UNCHANGED


def test_codex_agents_md_skips_diverging_without_force(tmp_path: pathlib.Path, claude_md: pathlib.Path):
    target = tmp_path / "codex" / "AGENTS.md"
    target.parent.mkdir(parents=True)
    target.write_text("hand-edited AGENTS.md\n")

    outcome = sync_codex_agents_md(target, claude_md)

    assert outcome.status == Status.SKIPPED
    assert target.read_text() == "hand-edited AGENTS.md\n"


def test_codex_agents_md_no_source_when_claude_md_missing(tmp_path: pathlib.Path):
    outcome = sync_codex_agents_md(tmp_path / "codex" / "AGENTS.md", tmp_path / "missing" / "CLAUDE.md")

    assert outcome.status == Status.NO_SOURCE


# ---- CLI ----


def test_cli_codex_config_creates_config(tmp_path: pathlib.Path, codex_home: pathlib.Path):
    codex_dir = tmp_path / "codex-target"
    result = runner.invoke(app, ["--claude-dir", str(codex_home), "--codex-dir", str(codex_dir), "codex", "config"])

    assert result.exit_code == 0
    assert (codex_dir / "config.toml").read_text() == CONFIG_TEMPLATE


def test_cli_codex_agents_md_creates_inlined(tmp_path: pathlib.Path, codex_home: pathlib.Path):
    codex_dir = tmp_path / "codex-target"
    result = runner.invoke(app, ["--claude-dir", str(codex_home), "--codex-dir", str(codex_dir), "codex", "agents-md"])

    assert result.exit_code == 0
    written = (codex_dir / "AGENTS.md").read_text()
    assert "the `uv` skill" in written
    assert "@skills/uv" not in written


def test_cli_codex_bare_runs_config_and_agents_md(tmp_path: pathlib.Path, codex_home: pathlib.Path):
    codex_dir = tmp_path / "codex-target"
    result = runner.invoke(app, ["--claude-dir", str(codex_home), "--codex-dir", str(codex_dir), "codex"])

    assert result.exit_code == 0
    assert (codex_dir / "config.toml").read_text() == CONFIG_TEMPLATE
    assert (codex_dir / "AGENTS.md").is_file()
