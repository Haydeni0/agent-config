import pathlib
import stat

import pytest
from typer.testing import CliRunner

import settings_sync.codex as codex
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
    (home / "harnesses/codex").mkdir(parents=True)
    (home / "harnesses/codex" / "config.toml").write_text(CONFIG_TEMPLATE)
    (home / "rules").mkdir(parents=True, exist_ok=True)
    (home / "rules/global.md").write_text("# Rules\nExtra rules.\nSee @skills/uv.\n")
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


def write_sqlite_template(path: pathlib.Path, sqlite_home: pathlib.Path) -> None:
    path.write_text(f'sqlite_home = "{sqlite_home}"\n')


def test_codex_sqlite_home_creates_private_directory(tmp_path: pathlib.Path):
    template = tmp_path / "config.toml"
    sqlite_home = tmp_path / "runtime" / "codex-sqlite"
    write_sqlite_template(template, sqlite_home)

    outcome = codex.sync_codex_sqlite_home(template)

    assert outcome.status == Status.CREATED
    assert stat.S_IMODE(sqlite_home.stat().st_mode) == 0o700


def test_codex_sqlite_home_repairs_permissions(tmp_path: pathlib.Path):
    template = tmp_path / "config.toml"
    sqlite_home = tmp_path / "codex-sqlite"
    sqlite_home.mkdir(mode=0o755)
    write_sqlite_template(template, sqlite_home)

    outcome = codex.sync_codex_sqlite_home(template)

    assert outcome.status == Status.REPLACED
    assert stat.S_IMODE(sqlite_home.stat().st_mode) == 0o700


def test_codex_sqlite_home_dry_run_creates_nothing(tmp_path: pathlib.Path):
    template = tmp_path / "config.toml"
    sqlite_home = tmp_path / "codex-sqlite"
    write_sqlite_template(template, sqlite_home)

    outcome = codex.sync_codex_sqlite_home(template, dry_run=True)

    assert outcome.status == Status.WOULD_CREATE
    assert not sqlite_home.exists()


def test_codex_sqlite_home_rejects_relative_path(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    template = tmp_path / "config.toml"
    template.write_text('sqlite_home = "relative/codex-sqlite"\n')

    outcome = codex.sync_codex_sqlite_home(template)

    assert outcome.status == Status.FAILED
    assert not (tmp_path / "relative").exists()


def test_codex_sqlite_home_rejects_symlink(tmp_path: pathlib.Path):
    template = tmp_path / "config.toml"
    real_directory = tmp_path / "real"
    real_directory.mkdir(mode=0o755)
    sqlite_home = tmp_path / "codex-sqlite"
    sqlite_home.symlink_to(real_directory, target_is_directory=True)
    write_sqlite_template(template, sqlite_home)

    outcome = codex.sync_codex_sqlite_home(template)

    assert outcome.status == Status.FAILED
    assert stat.S_IMODE(real_directory.stat().st_mode) == 0o755


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


def test_cli_codex_config_provisions_sqlite_home(tmp_path: pathlib.Path, codex_home: pathlib.Path):
    sqlite_home = tmp_path / "codex-sqlite"
    write_sqlite_template(codex_home / "harnesses/codex/config.toml", sqlite_home)
    codex_dir = tmp_path / "codex-target"

    result = runner.invoke(app, ["--claude-dir", str(codex_home), "--codex-dir", str(codex_dir), "codex", "config"])

    assert result.exit_code == 0
    assert sqlite_home.is_dir()
    assert stat.S_IMODE(sqlite_home.stat().st_mode) == 0o700


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
