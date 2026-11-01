from pathlib import Path
import copy
import pathlib

import pytest
from typer.testing import CliRunner

from settings_sync.actions import Mode, Regenerate, Status
from settings_sync.cli import agent_config_app
from settings_sync.executor import execute
from settings_sync.nomistakes import merge_yaml, plan_nomistakes_config
from settings_sync.ownership import OwnershipStore
from settings_sync.paths import resolve_paths


@pytest.fixture
def nm_template(tmp_path: pathlib.Path) -> pathlib.Path:
    """A shared-keys template at <claude>/no-mistakes/config.yaml."""
    source = tmp_path / "claude" / "harnesses" / "no-mistakes" / "config.yaml"
    source.parent.mkdir(parents=True)
    source.write_text("agent: claude\nreview_agent_timeout: \"30m\"\n")
    return source


@pytest.fixture
def nm_overlay(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """A machine overlay at <claude>/no-mistakes/config.local.yaml."""
    source = tmp_path / "cfg" / "agent-config" / "overlays" / "no-mistakes.yaml"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("agent_path_override:\n  claude: /usr/local/bin/local-claude\nworktree_roots: {}\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
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


# ---- plan_nomistakes_config ----

def _nm_paths(tmp_path: pathlib.Path) -> object:
    return resolve_paths(claude_dir=tmp_path / "claude", nomistakes_dir=tmp_path / "no-mistakes")


def _apply_nomistakes(paths, mode: Mode):
    store = OwnershipStore()
    store.load(mode)
    return execute(plan_nomistakes_config(paths), mode, store)




def test_config_creates_target_from_template_alone(nm_template, nm_target, tmp_path):
    outcome = _apply_nomistakes(_nm_paths(tmp_path), Mode.APPLY)[0]
    assert outcome.status == Status.CREATED
    assert "agent: claude" in nm_target.read_text()


def test_config_merges_overlay_and_overlay_wins(nm_template, nm_overlay, nm_target, tmp_path):
    nm_template.write_text("agent: claude\nagent_path_override:\n  codex: /usr/bin/codex\n")
    outcome = _apply_nomistakes(_nm_paths(tmp_path), Mode.APPLY)[0]
    assert outcome.status == Status.CREATED
    text = nm_target.read_text()
    assert "claude: /usr/local/bin/local-claude" in text
    assert "codex: /usr/bin/codex" in text
    assert "worktree_roots" in text


def test_config_absent_overlay_ok(nm_template, nm_target, nm_overlay, tmp_path):
    nm_overlay.unlink()
    outcome = _apply_nomistakes(_nm_paths(tmp_path), Mode.APPLY)[0]
    assert outcome.status == Status.CREATED
    assert "worktree_roots" not in nm_target.read_text()


def test_config_absent_template_fails_planning(nm_target, tmp_path):
    (tmp_path / "claude" / "harnesses" / "no-mistakes").mkdir(parents=True, exist_ok=True)
    (tmp_path / "claude" / "harnesses" / "no-mistakes" / "config.yaml").unlink(missing_ok=True)
    with pytest.raises(ValueError):
        plan_nomistakes_config(_nm_paths(tmp_path))
    assert not nm_target.exists()


def test_config_invalid_template_fails_target_untouched(nm_template, nm_overlay, nm_target, tmp_path):
    nm_target.parent.mkdir(parents=True)
    nm_target.write_text("existing: true\n")
    nm_template.write_text("agent: [unclosed\n")
    with pytest.raises(ValueError):
        plan_nomistakes_config(_nm_paths(tmp_path))
    assert nm_target.read_text() == "existing: true\n"


def test_config_invalid_overlay_fails_target_untouched(nm_template, nm_overlay, nm_target, tmp_path):
    nm_target.parent.mkdir(parents=True)
    nm_target.write_text("existing: true\n")
    nm_overlay.write_text("agent_path_override: [unclosed\n")
    with pytest.raises(ValueError):
        plan_nomistakes_config(_nm_paths(tmp_path))
    assert nm_target.read_text() == "existing: true\n"


def test_config_empty_files_treated_as_empty_dict(nm_template, nm_overlay, nm_target, tmp_path):
    nm_template.write_text("")
    nm_overlay.write_text("")
    outcome = _apply_nomistakes(_nm_paths(tmp_path), Mode.APPLY)[0]
    assert outcome.status == Status.CREATED
    assert nm_target.read_text().strip() == "{}"


def test_config_diverging_target_always_replaced(nm_template, nm_overlay, nm_target, tmp_path):
    nm_target.parent.mkdir(parents=True)
    nm_target.write_text("hand: edit\n")
    outcome = _apply_nomistakes(_nm_paths(tmp_path), Mode.APPLY)[0]
    assert outcome.status == Status.REPLACED
    assert "hand" not in nm_target.read_text()


def test_config_daemon_seed_target_replaced(nm_template, nm_overlay, nm_target, tmp_path):
    nm_target.parent.mkdir(parents=True)
    nm_target.write_text("# no-mistakes global configuration\nagent: auto\nci_timeout: \"168h\"\n" * 40)
    outcome = _apply_nomistakes(_nm_paths(tmp_path), Mode.APPLY)[0]
    assert outcome.status == Status.REPLACED


def test_config_invalid_yaml_target_heals(nm_template, nm_overlay, nm_target, tmp_path):
    nm_target.parent.mkdir(parents=True)
    nm_target.write_text("agent: [unclosed\n")
    outcome = _apply_nomistakes(_nm_paths(tmp_path), Mode.APPLY)[0]
    assert outcome.status == Status.REPLACED
    assert "agent: claude" in nm_target.read_text()


def test_config_dry_run_writes_nothing(nm_template, nm_overlay, nm_target, tmp_path):
    outcome = _apply_nomistakes(_nm_paths(tmp_path), Mode.DRY_RUN)[0]
    assert outcome.status == Status.WOULD_CREATE
    assert not nm_target.exists()


def test_config_dry_run_reports_drift(nm_template, nm_overlay, nm_target, tmp_path):
    nm_target.parent.mkdir(parents=True)
    nm_target.write_text("hand: edit\n")
    outcome = _apply_nomistakes(_nm_paths(tmp_path), Mode.DRY_RUN)[0]
    assert outcome.status == Status.WOULD_REPLACE
    assert nm_target.read_text() == "hand: edit\n"


def test_config_unchanged_when_identical(nm_template, nm_overlay, nm_target, tmp_path):
    _apply_nomistakes(_nm_paths(tmp_path), Mode.APPLY)
    outcome = _apply_nomistakes(_nm_paths(tmp_path), Mode.APPLY)[0]
    assert outcome.status == Status.UNCHANGED


# ---- Regenerate ----


def _regenerate(tmp_path, content: str, mode: Mode = Mode.APPLY):
    store = OwnershipStore()
    store.load(mode)
    return execute([Regenerate(tmp_path / "c.yaml", content)], mode, store)[0]


def test_regenerate_semantic_equality_reorder_is_unchanged(tmp_path):
    target = tmp_path / "c.yaml"
    target.write_text("b: 2\na: 1\n")
    store = OwnershipStore(); store.load(Mode.APPLY)
    outcome = execute([Regenerate(target, "a: 1\nb: 2\n")], Mode.APPLY, store)[0]
    assert outcome.status == Status.UNCHANGED


def test_sync_yaml_unparseable_target_replaced_under_force(tmp_path):
    target = tmp_path / "c.yaml"
    target.write_text("a: [unclosed\n")
    outcome = _regenerate(tmp_path, "a: 1\n", Mode.FORCE)
    assert outcome.status == Status.REPLACED


def test_sync_yaml_bare_no_scalar_quoted_round_trips_as_string(tmp_path):
    # pyyaml is YAML 1.1 (bare `no` loads as False) while no-mistakes parses
    # YAML 1.2 (stays a string) and rejects unknown types. The template must
    # quote such scalars; the round-trip then preserves the string.
    outcome = _regenerate(tmp_path, 'flag: "no"\n', Mode.FORCE)
    assert outcome.status == Status.CREATED
    assert '"no"' in (tmp_path / "c.yaml").read_text()


# ---- CLI ----


def test_cli_no_mistakes_end_to_end(tmp_path: Path, isolated_home: Path):
    claude = tmp_path / "claude"
    nm_dir = tmp_path / "no-mistakes"
    source = claude / "harnesses/no-mistakes" / "config.yaml"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("agent: claude\n")
    overlay = isolated_home / ".config/agent-config/overlays/no-mistakes.yaml"
    overlay.parent.mkdir(parents=True)
    overlay.write_text("agent_path_override:\n  claude: /usr/local/bin/local-claude\n")

    runner = CliRunner()
    result = runner.invoke(
        agent_config_app,
        [
            "--claude-dir", str(claude),
            "--opencode-dir", str(tmp_path / "opencode"),
            "--pi-dir", str(tmp_path / "pi"),
            "--goose-dir", str(tmp_path / "goose"),
            "--agy-dir", str(tmp_path / "agy"),
            "--nomistakes-dir", str(nm_dir),
            "sync", "no-mistakes",
        ],
    )
    assert result.exit_code == 0, result.output
    text = (nm_dir / "config.yaml").read_text()
    assert "agent: claude" in text
    assert "local-claude" in text


def test_cli_bare_sync_includes_nomistakes(tmp_path: Path, source_home: Path):
    claude = source_home
    nm_dir = tmp_path / "no-mistakes"
    source = claude / "harnesses/no-mistakes" / "config.yaml"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("agent: claude\n")
    (claude / "rules").mkdir(parents=True, exist_ok=True)
    (claude / "rules/global.md").write_text("# rules\n")

    runner = CliRunner()
    result = runner.invoke(
        agent_config_app,
        [
            "--claude-dir", str(claude),
            "--opencode-dir", str(tmp_path / "opencode"),
            "--pi-dir", str(tmp_path / "pi"),
            "--goose-dir", str(tmp_path / "goose"),
            "--agy-dir", str(tmp_path / "agy"),
            "--agy-cli-dir", str(tmp_path / "agy-cli"),
            "--nomistakes-dir", str(nm_dir),
            "--codex-dir", str(tmp_path / "codex"),
            "sync",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (nm_dir / "config.yaml").is_file()


def test_cli_check_reports_drift_nonzero(tmp_path):
    claude = tmp_path / "claude"
    nm_dir = tmp_path / "no-mistakes"
    source = claude / "harnesses/no-mistakes" / "config.yaml"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("agent: claude\n")
    nm_dir.mkdir()
    (nm_dir / "config.yaml").write_text("hand: edit\n")

    runner = CliRunner()
    result = runner.invoke(
        agent_config_app,
        [
            "--claude-dir", str(claude),
            "--opencode-dir", str(tmp_path / "opencode"),
            "--pi-dir", str(tmp_path / "pi"),
            "--nomistakes-dir", str(nm_dir),
            "check", "no-mistakes",
        ],
    )
    assert result.exit_code == 1
    assert (nm_dir / "config.yaml").read_text() == "hand: edit\n"
