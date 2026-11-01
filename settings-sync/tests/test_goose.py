from conftest import install_hook_sources
import json
import pathlib

import pytest
from typer.testing import CliRunner

from settings_sync.actions import Mode, Status
from settings_sync.cli import agent_config_app
from settings_sync.executor import execute
from settings_sync.goose import plan_goose_config, plan_goose_providers
from settings_sync.ownership import OwnershipStore
from settings_sync.paths import resolve_paths


@pytest.fixture
def goose_config(tmp_path: pathlib.Path) -> pathlib.Path:
    """A base config at <claude>/goose/config.yaml."""
    source = tmp_path / "claude" / "harnesses" / "goose" / "config.yaml"
    source.parent.mkdir(parents=True)
    source.write_text("GOOSE_TELEMETRY_ENABLED: false\n")
    return source


@pytest.fixture
def goose_providers(tmp_path: pathlib.Path) -> pathlib.Path:
    """A custom_providers dir at <claude>/goose/custom_providers/."""
    source = tmp_path / "claude" / "harnesses" / "goose" / "custom_providers"
    source.mkdir(parents=True)
    (source / "glm.json").write_text(json.dumps({"name": "glm", "engine": "openai", "base_url": "http://example/v1"}))
    return source


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




def _goose_paths(tmp_path: pathlib.Path):
    return resolve_paths(claude_dir=tmp_path / "claude", goose_dir=tmp_path / "goose")


def _apply(plan, paths, mode: Mode):
    store = OwnershipStore()
    store.load(mode)
    return execute(plan(paths), mode, store)


runner = CliRunner()


# ---- plan_goose_config ----


def test_goose_config_creates_from_source(tmp_path: pathlib.Path, goose_config: pathlib.Path):
    paths = _goose_paths(tmp_path)
    target = paths.goose_dir / "config.yaml"

    outcome = _apply(plan_goose_config, paths, Mode.APPLY)[0]

    assert outcome.status == Status.MERGED
    assert "GOOSE_TELEMETRY_ENABLED: false" in target.read_text()


def test_goose_config_unchanged_when_identical(tmp_path: pathlib.Path, goose_config: pathlib.Path):
    paths = _goose_paths(tmp_path)
    target = paths.goose_dir / "config.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(goose_config.read_text())

    outcome = _apply(plan_goose_config, paths, Mode.APPLY)[0]

    assert outcome.status == Status.UNCHANGED


def test_goose_config_merges_declared_keys(tmp_path: pathlib.Path, goose_config: pathlib.Path):
    paths = _goose_paths(tmp_path)
    target = paths.goose_dir / "config.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("GOOSE_TELEMETRY_ENABLED: true\n")

    outcome = _apply(plan_goose_config, paths, Mode.APPLY)[0]

    assert outcome.status == Status.MERGED
    assert "false" in target.read_text()


def test_goose_config_merges_under_force(tmp_path: pathlib.Path, goose_config: pathlib.Path):
    paths = _goose_paths(tmp_path)
    target = paths.goose_dir / "config.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("GOOSE_TELEMETRY_ENABLED: true\n")

    outcome = _apply(plan_goose_config, paths, Mode.FORCE)[0]

    assert outcome.status == Status.MERGED
    assert "GOOSE_TELEMETRY_ENABLED: false" in target.read_text()


def test_goose_config_no_source_when_missing(tmp_path: pathlib.Path):
    (tmp_path / "claude").mkdir(parents=True)
    paths = _goose_paths(tmp_path)

    with pytest.raises(OSError):
        plan_goose_config(paths)


# ---- plan_goose_providers ----


def test_goose_providers_creates_from_source(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    paths = _goose_paths(tmp_path)
    target_dir = paths.goose_dir / "custom_providers"

    outcomes = _apply(plan_goose_providers, paths, Mode.APPLY)

    glm = [o for o in outcomes if o.path.name == "glm.json"][0]
    assert glm.status == Status.CREATED
    written = json.loads((target_dir / "glm.json").read_text())
    assert written["name"] == "glm"


def test_goose_providers_unchanged_when_identical(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    paths = _goose_paths(tmp_path)
    target_dir = paths.goose_dir / "custom_providers"
    _apply(plan_goose_providers, paths, Mode.APPLY)

    outcomes = _apply(plan_goose_providers, paths, Mode.APPLY)

    glm = [o for o in outcomes if o.path.name == "glm.json"][0]
    assert glm.status == Status.UNCHANGED


def test_goose_providers_skips_diverging_without_force(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    paths = _goose_paths(tmp_path)
    target_dir = paths.goose_dir / "custom_providers"
    target_dir.mkdir(parents=True)
    (target_dir / "glm.json").write_text(json.dumps({"hand": "edited"}))

    outcomes = _apply(plan_goose_providers, paths, Mode.APPLY)

    glm = [o for o in outcomes if o.path.name == "glm.json"][0]
    assert glm.status == Status.SKIPPED
    assert json.loads((target_dir / "glm.json").read_text()) == {"hand": "edited"}


def test_goose_providers_force_overwrites_diverging(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    paths = _goose_paths(tmp_path)
    target_dir = paths.goose_dir / "custom_providers"
    target_dir.mkdir(parents=True)
    (target_dir / "glm.json").write_text(json.dumps({"hand": "edited"}))

    outcomes = _apply(plan_goose_providers, paths, Mode.FORCE)

    glm = [o for o in outcomes if o.path.name == "glm.json"][0]
    assert glm.status == Status.REPLACED
    assert json.loads((target_dir / "glm.json").read_text())["name"] == "glm"


def test_goose_providers_warns_on_orphan(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    paths = _goose_paths(tmp_path)
    target_dir = paths.goose_dir / "custom_providers"
    (goose_providers / "stale.json").write_text("{}")
    _apply(plan_goose_providers, paths, Mode.APPLY)
    (goose_providers / "stale.json").unlink()

    (target_dir / "stale.json").write_text('{"local": true}')

    outcomes = _apply(plan_goose_providers, paths, Mode.APPLY)

    orphan = [o for o in outcomes if o.path.name == "stale.json"][0]
    assert orphan.status == Status.WARNED
    assert (target_dir / "stale.json").exists()


def test_goose_providers_force_deletes_orphan(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    paths = _goose_paths(tmp_path)
    target_dir = paths.goose_dir / "custom_providers"
    (goose_providers / "stale.json").write_text("{}")
    _apply(plan_goose_providers, paths, Mode.APPLY)
    (goose_providers / "stale.json").unlink()

    outcomes = _apply(plan_goose_providers, paths, Mode.FORCE)

    orphan = [o for o in outcomes if o.path.name == "stale.json"][0]
    assert orphan.status == Status.REPLACED
    assert not (target_dir / "stale.json").exists()


def test_goose_providers_no_source_when_dir_missing(tmp_path: pathlib.Path):
    (tmp_path / "claude").mkdir(parents=True)
    paths = _goose_paths(tmp_path)

    outcomes = _apply(plan_goose_providers, paths, Mode.APPLY)

    assert outcomes[0].status == Status.NO_SOURCE


def test_goose_providers_dry_run_does_not_create_target_dir(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    """--dry-run must not create the target directory (read-only)."""
    paths = _goose_paths(tmp_path)
    target_dir = paths.goose_dir / "custom_providers"

    _apply(plan_goose_providers, paths, Mode.DRY_RUN)

    assert not target_dir.exists()


def test_goose_providers_dry_run_reports_orphan(tmp_path: pathlib.Path, goose_providers: pathlib.Path):
    """--dry-run should report orphans in an existing target dir without deleting."""
    paths = _goose_paths(tmp_path)
    target_dir = paths.goose_dir / "custom_providers"
    (goose_providers / "stale.json").write_text("{}")
    _apply(plan_goose_providers, paths, Mode.APPLY)
    (goose_providers / "stale.json").unlink()

    outcomes = _apply(plan_goose_providers, paths, Mode.DRY_RUN)

    orphan = [o for o in outcomes if o.path.name == "stale.json"][0]
    assert orphan.status == Status.WOULD_REPLACE
    assert (target_dir / "stale.json").exists()


# ---- CLI: sync goose ----


def test_cli_goose_hints_creates(tmp_path: pathlib.Path, goose_home: pathlib.Path):
    goose_dir = tmp_path / "goose-config"

    result = runner.invoke(agent_config_app, ["--claude-dir", str(goose_home), "--goose-dir", str(goose_dir), "sync", "goose", "hints"])

    assert result.exit_code == 0
    written = (goose_dir / ".goosehints").read_text()
    assert "Extra rules." in written
    assert "the `uv` skill" in written


def test_cli_goose_config_creates(tmp_path: pathlib.Path, goose_home: pathlib.Path):
    goose_dir = tmp_path / "goose-config"

    result = runner.invoke(agent_config_app, ["--claude-dir", str(goose_home), "--goose-dir", str(goose_dir), "sync", "goose", "config"])

    assert result.exit_code == 0
    assert (goose_dir / "config.yaml").read_text() == "GOOSE_TELEMETRY_ENABLED: false\n"


def test_cli_goose_providers_creates(tmp_path: pathlib.Path, goose_home: pathlib.Path):
    goose_dir = tmp_path / "goose-config"

    result = runner.invoke(agent_config_app, ["--claude-dir", str(goose_home), "--goose-dir", str(goose_dir), "sync", "goose", "providers"])

    assert result.exit_code == 0
    assert json.loads((goose_dir / "custom_providers" / "glm.json").read_text())["name"] == "glm"


def test_cli_goose_bare_runs_all_steps(tmp_path: pathlib.Path, goose_home: pathlib.Path):
    goose_dir = tmp_path / "goose-config"

    result = runner.invoke(agent_config_app, ["--claude-dir", str(goose_home), "--goose-dir", str(goose_dir), "sync", "goose"])

    assert result.exit_code == 0
    assert (goose_dir / ".goosehints").is_file()
    assert (goose_dir / "config.yaml").is_file()
    assert (goose_dir / "custom_providers" / "glm.json").is_file()


def test_cli_goose_config_check_detects_drift(tmp_path: pathlib.Path, goose_home: pathlib.Path):
    goose_dir = tmp_path / "goose-config"
    goose_dir.mkdir(parents=True)
    (goose_dir / "config.yaml").write_text("GOOSE_TELEMETRY_ENABLED: true\n")

    result = runner.invoke(agent_config_app, ["--check", "--claude-dir", str(goose_home), "--goose-dir", str(goose_dir), "check", "goose", "config"])

    assert result.exit_code != 0
    assert "true" in (goose_dir / "config.yaml").read_text()


def test_cli_all_includes_goose(tmp_path: pathlib.Path, source_home: pathlib.Path):
    """Bare `sync` (sync all) should include goose steps."""
    goose_dir = tmp_path / "goose-config"
    opencode_dir = tmp_path / "opencode"
    pi_dir = tmp_path / "pi-agent"

    result = runner.invoke(
        agent_config_app,
        [
            "--claude-dir", str(source_home),
            "--opencode-dir", str(opencode_dir),
            "--pi-dir", str(pi_dir),
            "--goose-dir", str(goose_dir),
            "--agy-dir", str(tmp_path / "gemini-config"),
            "--agy-cli-dir", str(tmp_path / "gemini-cli"),
            "--codex-dir", str(tmp_path / "codex"),
            "sync",
        ],
    )

    assert result.exit_code == 0
    assert (goose_dir / ".goosehints").is_file()
    assert (goose_dir / "config.yaml").is_file()
