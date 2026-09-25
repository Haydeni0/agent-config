from conftest import install_hook_sources
import json
import pathlib

import pytest
from typer.testing import CliRunner

from settings_sync.cli import app
from settings_sync.goose import sync_goose_config, sync_goose_hints, sync_goose_providers
from settings_sync.sync import Status


@pytest.fixture
def goose_config(tmp_path: pathlib.Path) -> pathlib.Path:
    """A base config at <claude>/goose/config.yaml."""
    source = tmp_path / "claude" / "goose" / "config.yaml"
    source.parent.mkdir(parents=True)
    source.write_text("GOOSE_TELEMETRY_ENABLED: false\n")
    return source


@pytest.fixture
def goose_providers(tmp_path: pathlib.Path) -> pathlib.Path:
    """A custom_providers dir at <claude>/goose/custom_providers/."""
    source = tmp_path / "claude" / "goose" / "custom_providers"
    source.mkdir(parents=True)
    (source / "glm.json").write_text(json.dumps({"name": "glm", "engine": "openai", "base_url": "http://example/v1"}))
    return source


@pytest.fixture
def claude_md(tmp_path: pathlib.Path) -> pathlib.Path:
    """A CLAUDE.md with an @skills/ reference."""
    claude_md = tmp_path / "claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True)
    claude_md.write_text("# Rules\nExtra rules.\nSee @skills/uv.\n")
    return claude_md


@pytest.fixture
def goose_home(tmp_path: pathlib.Path) -> pathlib.Path:
    """A full ~/.claude home with goose config, providers, CLAUDE.md, and a skill."""
    home = tmp_path / "claude"
    (home / "harnesses/goose").mkdir(parents=True)
    (home / "harnesses/goose" / "config.yaml").write_text("GOOSE_TELEMETRY_ENABLED: false\n")
    (home / "harnesses/goose" / "custom_providers").mkdir(parents=True)
    (home / "harnesses/goose" / "custom_providers" / "glm.json").write_text(
        json.dumps({"name": "glm", "engine": "openai", "base_url": "http://example/v1"})
    )
    (home / "rules").mkdir(parents=True, exist_ok=True)
    (home / "rules/global.md").write_text("# Rules\nExtra rules.\nSee @skills/uv.\n")
    (home / "skills").mkdir(parents=True)
    (home / "agents").mkdir()
    (home / "skills" / "uv").mkdir(parents=True)
    (home / "skills" / "uv" / "SKILL.md").write_text("---\nname: uv\ndescription: d\n---\nBody.\n")
    install_hook_sources(home)
    return home


runner = CliRunner()


# ---- sync_goose_hints (inlined CLAUDE.md; refuse-to-clobber without --force) ----


def test_goose_hints_creates_inlined(tmp_path: pathlib.Path, claude_md: pathlib.Path):
    target = tmp_path / "goose" / ".goosehints"

    outcome = sync_goose_hints(target, claude_md)

    assert outcome.status == Status.CREATED
    written = target.read_text()
    assert "Extra rules." in written
    assert "the `uv` skill" in written
    assert "@skills/uv" not in written


def test_goose_hints_unchanged_when_identical(tmp_path: pathlib.Path, claude_md: pathlib.Path):
    target = tmp_path / "goose" / ".goosehints"
    target.parent.mkdir(parents=True)
    sync_goose_hints(target, claude_md)

    outcome = sync_goose_hints(target, claude_md)

    assert outcome.status == Status.UNCHANGED


def test_goose_hints_skips_diverging_without_force(tmp_path: pathlib.Path, claude_md: pathlib.Path):
    target = tmp_path / "goose" / ".goosehints"
    target.parent.mkdir(parents=True)
    target.write_text("hand-edited hints\n")

    outcome = sync_goose_hints(target, claude_md)

    assert outcome.status == Status.SKIPPED
    assert target.read_text() == "hand-edited hints\n"


def test_goose_hints_force_overwrites_diverging(tmp_path: pathlib.Path, claude_md: pathlib.Path):
    target = tmp_path / "goose" / ".goosehints"
    target.parent.mkdir(parents=True)
    target.write_text("hand-edited hints\n")

    outcome = sync_goose_hints(target, claude_md, force=True)

    assert outcome.status == Status.REPLACED
    assert "# Rules" in target.read_text()


def test_goose_hints_no_source_when_claude_md_missing(tmp_path: pathlib.Path):
    outcome = sync_goose_hints(tmp_path / "goose" / ".goosehints", tmp_path / "missing" / "CLAUDE.md")

    assert outcome.status == Status.NO_SOURCE


# ---- sync_goose_config (refuse-to-clobber without --force) ----


def test_goose_config_creates_from_source(tmp_path: pathlib.Path, goose_config: pathlib.Path):
    target = tmp_path / "goose" / "config.yaml"

    outcome = sync_goose_config(target, goose_config)

    assert outcome.status == Status.CREATED
    assert target.read_text() == "GOOSE_TELEMETRY_ENABLED: false\n"


def test_goose_config_unchanged_when_identical(tmp_path: pathlib.Path, goose_config: pathlib.Path):
    target = tmp_path / "goose" / "config.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(goose_config.read_text())

    outcome = sync_goose_config(target, goose_config)

    assert outcome.status == Status.UNCHANGED


def test_goose_config_updates_declared_keys(tmp_path: pathlib.Path, goose_config: pathlib.Path):
    target = tmp_path / "goose" / "config.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("GOOSE_TELEMETRY_ENABLED: true\n")

    outcome = sync_goose_config(target, goose_config)

    assert outcome.status == Status.REPLACED
    assert "false" in target.read_text()


def test_goose_config_force_overwrites_diverging(tmp_path: pathlib.Path, goose_config: pathlib.Path):
    target = tmp_path / "goose" / "config.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("GOOSE_TELEMETRY_ENABLED: true\n")

    outcome = sync_goose_config(target, goose_config, force=True)

    assert outcome.status == Status.REPLACED
    assert target.read_text() == "GOOSE_TELEMETRY_ENABLED: false\n"


def test_goose_config_no_source_when_missing(tmp_path: pathlib.Path):
    outcome = sync_goose_config(tmp_path / "goose" / "config.yaml", tmp_path / "missing" / "config.yaml")

    assert outcome.status == Status.NO_SOURCE


# ---- sync_goose_providers (dir sync with orphan handling) ----


def test_goose_providers_creates_from_source(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    target_dir = tmp_path / "goose" / "custom_providers"

    outcomes = sync_goose_providers(target_dir, goose_providers)

    assert outcomes[0].status == Status.CREATED
    written = json.loads((target_dir / "glm.json").read_text())
    assert written["name"] == "glm"


def test_goose_providers_unchanged_when_identical(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    target_dir = tmp_path / "goose" / "custom_providers"
    sync_goose_providers(target_dir, goose_providers)

    outcomes = sync_goose_providers(target_dir, goose_providers)

    assert outcomes[0].status == Status.UNCHANGED


def test_goose_providers_skips_diverging_without_force(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    target_dir = tmp_path / "goose" / "custom_providers"
    target_dir.mkdir(parents=True)
    (target_dir / "glm.json").write_text(json.dumps({"hand": "edited"}))

    outcomes = sync_goose_providers(target_dir, goose_providers)

    assert outcomes[0].status == Status.SKIPPED
    assert json.loads((target_dir / "glm.json").read_text()) == {"hand": "edited"}


def test_goose_providers_force_overwrites_diverging(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    target_dir = tmp_path / "goose" / "custom_providers"
    target_dir.mkdir(parents=True)
    (target_dir / "glm.json").write_text(json.dumps({"hand": "edited"}))

    outcomes = sync_goose_providers(target_dir, goose_providers, force=True)

    assert outcomes[0].status == Status.REPLACED
    assert json.loads((target_dir / "glm.json").read_text())["name"] == "glm"


def test_goose_providers_warns_on_orphan(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    target_dir = tmp_path / "goose" / "custom_providers"
    (goose_providers / "stale.json").write_text("{}")
    sync_goose_providers(target_dir, goose_providers)
    (goose_providers / "stale.json").unlink()

    (target_dir / "stale.json").write_text('{"local": true}')

    outcomes = sync_goose_providers(target_dir, goose_providers)

    orphan = [o for o in outcomes if o.path.name == "stale.json"][0]
    assert orphan.status == Status.WARNED
    assert (target_dir / "stale.json").exists()


def test_goose_providers_force_deletes_orphan(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    target_dir = tmp_path / "goose" / "custom_providers"
    (goose_providers / "stale.json").write_text("{}")
    sync_goose_providers(target_dir, goose_providers)
    (goose_providers / "stale.json").unlink()

    outcomes = sync_goose_providers(target_dir, goose_providers, force=True)

    orphan = [o for o in outcomes if o.path.name == "stale.json"][0]
    assert orphan.status == Status.REPLACED
    assert not (target_dir / "stale.json").exists()


def test_goose_providers_no_source_when_dir_missing(tmp_path: pathlib.Path):
    outcomes = sync_goose_providers(tmp_path / "goose" / "custom_providers", tmp_path / "missing")

    assert outcomes[0].status == Status.NO_SOURCE


def test_goose_providers_dry_run_does_not_create_target_dir(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    """--dry-run must not create the target directory (read-only)."""
    target_dir = tmp_path / "goose" / "custom_providers"

    outcomes = sync_goose_providers(target_dir, goose_providers, dry_run=True)

    assert not target_dir.exists()


def test_goose_providers_dry_run_reports_orphan(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    """--dry-run should report orphans in an existing target dir without deleting."""
    target_dir = tmp_path / "goose" / "custom_providers"
    (goose_providers / "stale.json").write_text("{}")
    sync_goose_providers(target_dir, goose_providers)
    (goose_providers / "stale.json").unlink()

    outcomes = sync_goose_providers(target_dir, goose_providers, dry_run=True)

    orphan = [o for o in outcomes if o.path.name == "stale.json"][0]
    assert orphan.status == Status.WOULD_REPLACE
    assert (target_dir / "stale.json").exists()


# ---- CLI: sync goose ----


def test_cli_goose_hints_creates(tmp_path: pathlib.Path, goose_home: pathlib.Path):
    goose_dir = tmp_path / "goose-config"

    result = runner.invoke(app, ["--claude-dir", str(goose_home), "--goose-dir", str(goose_dir), "goose", "hints"])

    assert result.exit_code == 0
    written = (goose_dir / ".goosehints").read_text()
    assert "Extra rules." in written
    assert "the `uv` skill" in written


def test_cli_goose_config_creates(tmp_path: pathlib.Path, goose_home: pathlib.Path):
    goose_dir = tmp_path / "goose-config"

    result = runner.invoke(app, ["--claude-dir", str(goose_home), "--goose-dir", str(goose_dir), "goose", "config"])

    assert result.exit_code == 0
    assert (goose_dir / "config.yaml").read_text() == "GOOSE_TELEMETRY_ENABLED: false\n"


def test_cli_goose_providers_creates(tmp_path: pathlib.Path, goose_home: pathlib.Path):
    goose_dir = tmp_path / "goose-config"

    result = runner.invoke(app, ["--claude-dir", str(goose_home), "--goose-dir", str(goose_dir), "goose", "providers"])

    assert result.exit_code == 0
    assert json.loads((goose_dir / "custom_providers" / "glm.json").read_text())["name"] == "glm"


def test_cli_goose_bare_runs_all_steps(tmp_path: pathlib.Path, goose_home: pathlib.Path):
    goose_dir = tmp_path / "goose-config"

    result = runner.invoke(app, ["--claude-dir", str(goose_home), "--goose-dir", str(goose_dir), "goose"])

    assert result.exit_code == 0
    assert (goose_dir / ".goosehints").is_file()
    assert (goose_dir / "config.yaml").is_file()
    assert (goose_dir / "custom_providers" / "glm.json").is_file()


def test_cli_goose_config_check_detects_drift(tmp_path: pathlib.Path, goose_home: pathlib.Path):
    goose_dir = tmp_path / "goose-config"
    goose_dir.mkdir(parents=True)
    (goose_dir / "config.yaml").write_text("GOOSE_TELEMETRY_ENABLED: true\n")

    result = runner.invoke(app, ["--check", "--claude-dir", str(goose_home), "--goose-dir", str(goose_dir), "goose", "config"])

    assert result.exit_code != 0
    assert "true" in (goose_dir / "config.yaml").read_text()


def test_cli_all_includes_goose(tmp_path: pathlib.Path, source_home: pathlib.Path):
    """Bare `sync` (sync all) should include goose steps."""
    goose_dir = tmp_path / "goose-config"
    opencode_dir = tmp_path / "opencode"
    pi_dir = tmp_path / "pi-agent"

    result = runner.invoke(
        app,
        [
            "--claude-dir", str(source_home),
            "--opencode-dir", str(opencode_dir),
            "--pi-dir", str(pi_dir),
            "--goose-dir", str(goose_dir),
            "--agy-dir", str(tmp_path / "gemini-config"),
            "--agy-cli-dir", str(tmp_path / "gemini-cli"),
            "--codex-dir", str(tmp_path / "codex"),
            "all",
        ],
    )

    assert result.exit_code == 0
    assert (goose_dir / ".goosehints").is_file()
    assert (goose_dir / "config.yaml").is_file()
