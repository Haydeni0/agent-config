from conftest import install_hook_sources
import pathlib
import stat

import pytest
from typer.testing import CliRunner

import settings_sync.codex as codex
from settings_sync.actions import Mode, Status
from settings_sync.registry import HARNESSES
from settings_sync.cli import agent_config_app
from settings_sync.codex import plan_codex_config
from settings_sync.executor import execute
from settings_sync.ownership import OwnershipStore
from settings_sync.paths import resolve_paths

CONFIG_TEMPLATE = '[features]\nhooks = true\n'


@pytest.fixture
def codex_template(tmp_path: pathlib.Path) -> pathlib.Path:
    """A config template at <claude>/codex/config.toml."""
    template = tmp_path / "claude" / "harnesses" / "codex" / "config.toml"
    template.parent.mkdir(parents=True)
    template.write_text(CONFIG_TEMPLATE)
    return template


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
    install_hook_sources(home)
    return home




def _codex_paths(tmp_path: pathlib.Path):
    return resolve_paths(HARNESSES, claude_dir=tmp_path / "claude", codex_dir=tmp_path / "codex-target")


def _apply_config(paths, mode: Mode):
    store = OwnershipStore()
    store.load(mode)
    return execute(plan_codex_config(paths), mode, store)


runner = CliRunner()


# ---- plan_codex_config ----


def test_codex_config_creates_from_template(tmp_path: pathlib.Path, codex_template: pathlib.Path):
    paths = _codex_paths(tmp_path)
    target = paths.codex_dir / "config.toml"

    outcomes = _apply_config(paths, Mode.APPLY)
    outcome = next(o for o in outcomes if o.path == target)

    assert outcome.status == Status.MERGED
    assert target.read_text() == CONFIG_TEMPLATE


def test_codex_config_updates_managed_keys(tmp_path: pathlib.Path, codex_template: pathlib.Path):
    paths = _codex_paths(tmp_path)
    target = paths.codex_dir / "config.toml"
    target.parent.mkdir(parents=True)
    target.write_text('[features]\nhooks = false\n')

    outcomes = _apply_config(paths, Mode.APPLY)
    outcome = next(o for o in outcomes if o.path == target)

    assert outcome.status == Status.MERGED
    assert target.read_text() == CONFIG_TEMPLATE


def test_codex_config_dry_run_preserves_config(tmp_path: pathlib.Path, codex_template: pathlib.Path):
    paths = _codex_paths(tmp_path)
    target = paths.codex_dir / "config.toml"
    target.parent.mkdir(parents=True)
    target.write_text('[features]\nhooks = false\n')

    outcomes = _apply_config(paths, Mode.DRY_RUN)
    outcome = next(o for o in outcomes if o.path == target)

    assert outcome.status == Status.WOULD_MERGE
    assert target.read_text() == '[features]\nhooks = false\n'


def test_codex_config_unchanged_when_identical(tmp_path: pathlib.Path, codex_template: pathlib.Path):
    paths = _codex_paths(tmp_path)
    target = paths.codex_dir / "config.toml"
    target.parent.mkdir(parents=True)
    target.write_text(CONFIG_TEMPLATE)

    outcomes = _apply_config(paths, Mode.APPLY)
    outcome = next(o for o in outcomes if o.path == target)

    assert outcome.status == Status.UNCHANGED


@pytest.mark.parametrize("dry_status", [(True, Status.WOULD_CREATE), (False, Status.MERGED)])
def test_codex_config_dry_run_creates_nothing(tmp_path: pathlib.Path, codex_template: pathlib.Path, dry_status: tuple[bool, Status]):
    dry_run, expected = dry_status
    paths = _codex_paths(tmp_path)
    target = paths.codex_dir / "config.toml"

    outcomes = _apply_config(paths, Mode.DRY_RUN if dry_run else Mode.APPLY)
    outcome = next(o for o in outcomes if o.path == target)

    assert outcome.status == expected
    assert (not target.exists()) if dry_run else target.exists()


def test_codex_config_no_source_when_template_missing(tmp_path: pathlib.Path):
    (tmp_path / "claude").mkdir(parents=True)
    paths = _codex_paths(tmp_path)

    with pytest.raises(OSError):
        plan_codex_config(paths)


def write_sqlite_template(path: pathlib.Path, sqlite_home: pathlib.Path) -> None:
    path.write_text(f'sqlite_home = "{sqlite_home}"\n')


def test_codex_sqlite_home_creates_private_directory(tmp_path: pathlib.Path):
    template = tmp_path / "claude" / "harnesses" / "codex" / "config.toml"
    template.parent.mkdir(parents=True)
    sqlite_home = tmp_path / "runtime" / "codex-sqlite"
    write_sqlite_template(template, sqlite_home)
    paths = resolve_paths(HARNESSES, claude_dir=tmp_path / "claude", codex_dir=tmp_path / "codex-target")

    outcomes = _apply_config(paths, Mode.APPLY)
    outcome = next(o for o in outcomes if o.path == sqlite_home)

    assert outcome.status == Status.CREATED
    assert stat.S_IMODE(sqlite_home.stat().st_mode) == 0o700


def test_codex_sqlite_home_repairs_permissions(tmp_path: pathlib.Path):
    template = tmp_path / "claude" / "harnesses" / "codex" / "config.toml"
    template.parent.mkdir(parents=True)
    sqlite_home = tmp_path / "codex-sqlite"
    sqlite_home.mkdir(mode=0o755)
    write_sqlite_template(template, sqlite_home)
    paths = resolve_paths(HARNESSES, claude_dir=tmp_path / "claude", codex_dir=tmp_path / "codex-target")

    outcomes = _apply_config(paths, Mode.APPLY)
    outcome = next(o for o in outcomes if o.path == sqlite_home)

    assert outcome.status == Status.REPLACED
    assert stat.S_IMODE(sqlite_home.stat().st_mode) == 0o700


def test_codex_sqlite_home_dry_run_creates_nothing(tmp_path: pathlib.Path):
    template = tmp_path / "claude" / "harnesses" / "codex" / "config.toml"
    template.parent.mkdir(parents=True)
    sqlite_home = tmp_path / "codex-sqlite"
    write_sqlite_template(template, sqlite_home)
    paths = resolve_paths(HARNESSES, claude_dir=tmp_path / "claude", codex_dir=tmp_path / "codex-target")

    outcomes = _apply_config(paths, Mode.DRY_RUN)
    outcome = next(o for o in outcomes if o.path == sqlite_home)

    assert outcome.status == Status.WOULD_CREATE
    assert not sqlite_home.exists()


def test_codex_sqlite_home_rejects_relative_path(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    template = tmp_path / "claude" / "harnesses" / "codex" / "config.toml"
    template.parent.mkdir(parents=True)
    template.write_text('sqlite_home = "relative/codex-sqlite"\n')
    paths = resolve_paths(HARNESSES, claude_dir=tmp_path / "claude", codex_dir=tmp_path / "codex-target")

    with pytest.raises(ValueError):
        plan_codex_config(paths)

    assert not (tmp_path / "relative").exists()


def test_codex_sqlite_home_rejects_symlink(tmp_path: pathlib.Path):
    template = tmp_path / "claude" / "harnesses" / "codex" / "config.toml"
    template.parent.mkdir(parents=True)
    real_directory = tmp_path / "real"
    real_directory.mkdir(mode=0o755)
    sqlite_home = tmp_path / "codex-sqlite"
    sqlite_home.symlink_to(real_directory, target_is_directory=True)
    write_sqlite_template(template, sqlite_home)
    paths = resolve_paths(HARNESSES, claude_dir=tmp_path / "claude", codex_dir=tmp_path / "codex-target")

    with pytest.raises(ValueError):
        plan_codex_config(paths)

    assert stat.S_IMODE(real_directory.stat().st_mode) == 0o755


# ---- CLI ----


def test_cli_codex_config_creates_config(tmp_path: pathlib.Path, codex_home: pathlib.Path):
    codex_dir = tmp_path / "codex-target"
    result = runner.invoke(agent_config_app, ["--claude-dir", str(codex_home), "--codex-dir", str(codex_dir), "sync", "codex", "config"])

    assert result.exit_code == 0
    assert (codex_dir / "config.toml").read_text() == CONFIG_TEMPLATE


def test_cli_codex_config_provisions_sqlite_home(tmp_path: pathlib.Path, codex_home: pathlib.Path):
    sqlite_home = tmp_path / "codex-sqlite"
    write_sqlite_template(codex_home / "harnesses/codex/config.toml", sqlite_home)
    codex_dir = tmp_path / "codex-target"

    result = runner.invoke(agent_config_app, ["--claude-dir", str(codex_home), "--codex-dir", str(codex_dir), "sync", "codex", "config"])

    assert result.exit_code == 0
    assert sqlite_home.is_dir()
    assert stat.S_IMODE(sqlite_home.stat().st_mode) == 0o700


def test_cli_codex_agents_md_creates_inlined(tmp_path: pathlib.Path, codex_home: pathlib.Path):
    codex_dir = tmp_path / "codex-target"
    result = runner.invoke(agent_config_app, ["--claude-dir", str(codex_home), "--codex-dir", str(codex_dir), "sync", "codex", "agents-md"])

    assert result.exit_code == 0
    written = (codex_dir / "AGENTS.md").read_text()
    assert "the `uv` skill" in written
    assert "@skills/uv" not in written


def test_cli_codex_bare_runs_config_and_agents_md(tmp_path: pathlib.Path, codex_home: pathlib.Path):
    codex_dir = tmp_path / "codex-target"
    result = runner.invoke(agent_config_app, ["--claude-dir", str(codex_home), "--codex-dir", str(codex_dir), "sync", "codex"])

    assert result.exit_code == 0
    assert (codex_dir / "config.toml").read_text() == CONFIG_TEMPLATE
    assert (codex_dir / "AGENTS.md").is_file()
