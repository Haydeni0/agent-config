import copy
import pathlib

import pytest
from typer.testing import CliRunner

from settings_sync.cli import app
from settings_sync.nomistakes import merge_yaml, sync_nomistakes_config
from settings_sync.sync import Status, sync_yaml


@pytest.fixture
def nm_template(tmp_path: pathlib.Path) -> pathlib.Path:
    """A shared-keys template at <claude>/no-mistakes/config.yaml."""
    source = tmp_path / "claude" / "no-mistakes" / "config.yaml"
    source.parent.mkdir(parents=True)
    source.write_text("agent: claude\nreview_agent_timeout: \"30m\"\n")
    return source


@pytest.fixture
def nm_overlay(tmp_path: pathlib.Path) -> pathlib.Path:
    """A machine overlay at <claude>/no-mistakes/config.local.yaml."""
    source = tmp_path / "claude" / "no-mistakes" / "config.local.yaml"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("agent_path_override:\n  claude: /usr/local/bin/local-claude\nworktree_roots: {}\n")
    return source


@pytest.fixture
def nm_target(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "no-mistakes" / "config.yaml"


# ---- merge_yaml ----


def test_merge_yaml_recursive_dict_merge():
    base = {"a": {"x": 1, "y": 2}, "b": 1}
    overlay = {"a": {"y": 3, "z": 4}}
    assert merge_yaml(base, overlay) == {"a": {"x": 1, "y": 3, "z": 4}, "b": 1}


def test_merge_yaml_scalar_list_null_replace():
    base = {"a": 1, "b": [1, 2], "c": "keep", "d": "gone"}
    overlay = {"a": 2, "b": [3], "d": None}
    assert merge_yaml(base, overlay) == {"a": 2, "b": [3], "c": "keep", "d": None}


def test_merge_yaml_type_change_replaces():
    assert merge_yaml({"a": {"x": 1}}, {"a": 5}) == {"a": 5}
    assert merge_yaml({"a": 5}, {"a": {"x": 1}}) == {"a": {"x": 1}}


def test_merge_yaml_empty_overlay_returns_base_copy():
    base = {"a": {"x": 1}}
    merged = merge_yaml(base, {})
    assert merged == base
    assert merged is not base
    assert merged["a"] is not base["a"]


def test_merge_yaml_disjoint_union():
    assert merge_yaml({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_merge_yaml_does_not_mutate_inputs():
    base = {"a": {"x": 1, "y": 2}}
    overlay = {"a": {"y": 3}}
    base_copy = copy.deepcopy(base)
    overlay_copy = copy.deepcopy(overlay)
    merge_yaml(base, overlay)
    assert base == base_copy
    assert overlay == overlay_copy


def test_merge_yaml_empty_template_with_overlay():
    assert merge_yaml({}, {"a": 1}) == {"a": 1}


# ---- sync_nomistakes_config ----


def test_config_creates_target_from_template_alone(nm_template, nm_target):
    outcome = sync_nomistakes_config(nm_target, nm_template, nm_template.with_name("config.local.yaml"))
    assert outcome.status == Status.CREATED
    assert "agent: claude" in nm_target.read_text()


def test_config_merges_overlay_and_overlay_wins(nm_template, nm_overlay, nm_target):
    nm_template.write_text("agent: claude\nagent_path_override:\n  codex: /usr/bin/codex\n")
    outcome = sync_nomistakes_config(nm_target, nm_template, nm_overlay)
    assert outcome.status == Status.CREATED
    text = nm_target.read_text()
    assert "claude: /usr/local/bin/local-claude" in text
    assert "codex: /usr/bin/codex" in text
    assert "worktree_roots" in text


def test_config_absent_overlay_ok(nm_template, nm_target):
    outcome = sync_nomistakes_config(nm_target, nm_template, nm_template.with_name("config.local.yaml"))
    assert outcome.status == Status.CREATED
    assert "worktree_roots" not in nm_target.read_text()


def test_config_absent_template_is_no_source(nm_target):
    outcome = sync_nomistakes_config(nm_target, pathlib.Path("/nonexistent/config.yaml"), pathlib.Path("/nonexistent/local.yaml"))
    assert outcome.status == Status.NO_SOURCE
    assert not nm_target.exists()


def test_config_invalid_template_fails_target_untouched(nm_template, nm_overlay, nm_target):
    nm_target.parent.mkdir(parents=True)
    nm_target.write_text("existing: true\n")
    nm_template.write_text("agent: [unclosed\n")
    outcome = sync_nomistakes_config(nm_target, nm_template, nm_overlay)
    assert outcome.status == Status.FAILED
    assert nm_target.read_text() == "existing: true\n"


def test_config_invalid_overlay_fails_target_untouched(nm_template, nm_overlay, nm_target):
    nm_target.parent.mkdir(parents=True)
    nm_target.write_text("existing: true\n")
    nm_overlay.write_text("agent_path_override: [unclosed\n")
    outcome = sync_nomistakes_config(nm_target, nm_template, nm_overlay)
    assert outcome.status == Status.FAILED
    assert nm_target.read_text() == "existing: true\n"


def test_config_empty_files_treated_as_empty_dict(nm_template, nm_overlay, nm_target):
    nm_template.write_text("")
    nm_overlay.write_text("")
    outcome = sync_nomistakes_config(nm_target, nm_template, nm_overlay)
    assert outcome.status == Status.CREATED
    assert nm_target.read_text().strip() == "{}"


def test_config_diverging_target_always_replaced(nm_template, nm_overlay, nm_target):
    nm_target.parent.mkdir(parents=True)
    nm_target.write_text("hand: edit\n")
    outcome = sync_nomistakes_config(nm_target, nm_template, nm_overlay)
    assert outcome.status == Status.REPLACED
    assert "hand" not in nm_target.read_text()


def test_config_daemon_seed_target_replaced(nm_template, nm_overlay, nm_target):
    nm_target.parent.mkdir(parents=True)
    nm_target.write_text("# no-mistakes global configuration\nagent: auto\nci_timeout: \"168h\"\n" * 40)
    outcome = sync_nomistakes_config(nm_target, nm_template, nm_overlay)
    assert outcome.status == Status.REPLACED


def test_config_invalid_yaml_target_heals(nm_template, nm_overlay, nm_target):
    nm_target.parent.mkdir(parents=True)
    nm_target.write_text("agent: [unclosed\n")
    outcome = sync_nomistakes_config(nm_target, nm_template, nm_overlay)
    assert outcome.status == Status.REPLACED
    assert "agent: claude" in nm_target.read_text()


def test_config_dry_run_writes_nothing(nm_template, nm_overlay, nm_target):
    outcome = sync_nomistakes_config(nm_target, nm_template, nm_overlay, dry_run=True)
    assert outcome.status == Status.WOULD_CREATE
    assert not nm_target.exists()


def test_config_dry_run_reports_drift(nm_template, nm_overlay, nm_target):
    nm_target.parent.mkdir(parents=True)
    nm_target.write_text("hand: edit\n")
    outcome = sync_nomistakes_config(nm_target, nm_template, nm_overlay, dry_run=True)
    assert outcome.status == Status.WOULD_REPLACE
    assert nm_target.read_text() == "hand: edit\n"


def test_config_unchanged_when_identical(nm_template, nm_overlay, nm_target):
    sync_nomistakes_config(nm_target, nm_template, nm_overlay)
    outcome = sync_nomistakes_config(nm_target, nm_template, nm_overlay)
    assert outcome.status == Status.UNCHANGED


# ---- sync_yaml ----


def test_sync_yaml_semantic_equality_reorder_is_unchanged(tmp_path):
    target = tmp_path / "c.yaml"
    target.write_text("b: 2\na: 1\n")
    outcome = sync_yaml(target, "a: 1\nb: 2\n")
    assert outcome.status == Status.UNCHANGED


def test_sync_yaml_drift_skipped_without_force(tmp_path):
    target = tmp_path / "c.yaml"
    target.write_text("a: 1\n")
    outcome = sync_yaml(target, "a: 2\n")
    assert outcome.status == Status.SKIPPED
    assert target.read_text() == "a: 1\n"


def test_sync_yaml_drift_replaced_with_force(tmp_path):
    target = tmp_path / "c.yaml"
    target.write_text("a: 1\n")
    outcome = sync_yaml(target, "a: 2\n", force=True)
    assert outcome.status == Status.REPLACED
    assert target.read_text() == "a: 2\n"


def test_sync_yaml_unparseable_target_replaced_under_force(tmp_path):
    target = tmp_path / "c.yaml"
    target.write_text("a: [unclosed\n")
    outcome = sync_yaml(target, "a: 1\n", force=True)
    assert outcome.status == Status.REPLACED


def test_sync_yaml_bare_no_scalar_quoted_round_trips_as_string(tmp_path):
    # pyyaml is YAML 1.1 (bare `no` loads as False) while no-mistakes parses
    # YAML 1.2 (stays a string) and rejects unknown types. The template must
    # quote such scalars; the round-trip then preserves the string.
    target = tmp_path / "c.yaml"
    outcome = sync_yaml(target, 'flag: "no"\n', force=True)
    assert outcome.status == Status.CREATED
    assert '"no"' in target.read_text()


# ---- CLI ----


def test_cli_no_mistakes_end_to_end(tmp_path):
    claude = tmp_path / "claude"
    nm_dir = tmp_path / "no-mistakes"
    source = claude / "no-mistakes" / "config.yaml"
    source.parent.mkdir(parents=True)
    source.write_text("agent: claude\n")
    (claude / "no-mistakes" / "config.local.yaml").write_text("agent_path_override:\n  claude: /usr/local/bin/local-claude\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--claude-dir", str(claude),
            "--opencode-dir", str(tmp_path / "opencode"),
            "--pi-dir", str(tmp_path / "pi"),
            "--goose-dir", str(tmp_path / "goose"),
            "--agy-dir", str(tmp_path / "agy"),
            "--nomistakes-dir", str(nm_dir),
            "no-mistakes",
        ],
    )
    assert result.exit_code == 0, result.output
    text = (nm_dir / "config.yaml").read_text()
    assert "agent: claude" in text
    assert "local-claude" in text


def test_cli_bare_sync_includes_nomistakes(tmp_path):
    claude = tmp_path / "claude"
    nm_dir = tmp_path / "no-mistakes"
    source = claude / "no-mistakes" / "config.yaml"
    source.parent.mkdir(parents=True)
    source.write_text("agent: claude\n")
    (claude / "CLAUDE.md").write_text("# rules\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--claude-dir", str(claude),
            "--opencode-dir", str(tmp_path / "opencode"),
            "--pi-dir", str(tmp_path / "pi"),
            "--goose-dir", str(tmp_path / "goose"),
            "--agy-dir", str(tmp_path / "agy"),
            "--agy-cli-dir", str(tmp_path / "agy-cli"),
            "--nomistakes-dir", str(nm_dir),
            "--codex-dir", str(tmp_path / "codex"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (nm_dir / "config.yaml").is_file()


def test_cli_check_reports_drift_nonzero(tmp_path):
    claude = tmp_path / "claude"
    nm_dir = tmp_path / "no-mistakes"
    source = claude / "no-mistakes" / "config.yaml"
    source.parent.mkdir(parents=True)
    source.write_text("agent: claude\n")
    nm_dir.mkdir()
    (nm_dir / "config.yaml").write_text("hand: edit\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--claude-dir", str(claude),
            "--opencode-dir", str(tmp_path / "opencode"),
            "--pi-dir", str(tmp_path / "pi"),
            "--nomistakes-dir", str(nm_dir),
            "no-mistakes",
            "--check",
        ],
    )
    assert result.exit_code == 1
    assert (nm_dir / "config.yaml").read_text() == "hand: edit\n"
