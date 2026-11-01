"""Key-level template ownership: dropped keys removed when unedited (REQ-SYNC-14)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from settings_sync.cli import agent_config_app


def test_leaf_paths_shape() -> None:
    from settings_sync.merging import leaf_paths
    value = {"a": {"b": [1, {"c": 2}]}, "d": None, "e": {}, "f.g": 1}
    assert leaf_paths(value) == {("a", "b"), ("d",), ("e",), ("f.g",)}


STEPS = [
    ("agy", "settings", ".gemini/antigravity-cli/settings.json", "json"),
    ("goose", "config", ".config/goose/config.yaml", "yaml"),
    ("codex", "config", ".codex/config.toml", "toml"),
]


def _declare(source_home: Path, harness: str, body: str) -> None:
    template = {"agy": "harnesses/gemini/settings.json", "goose": "harnesses/goose/config.yaml",
                "codex": "harnesses/codex/config.toml"}[harness]
    (source_home / template).write_text(body)


def test_dropped_key_removed_per_codec(source_home: Path, isolated_home: Path) -> None:
    """S1: extra disappears when unchanged; every other key intact, exit 0."""
    bodies = {
        "agy": '{"model": "shared", "extra": 1}',
        "goose": "model: shared\nextra: 1\n",
        "codex": 'model = "shared"\nextra = 1\n',
    }
    drops = {
        "agy": '{"model": "shared"}',
        "goose": "model: shared\n",
        "codex": 'model = "shared"\n',
    }
    for harness, step, target, _codec in STEPS:
        _declare(source_home, harness, bodies[harness])
        args = ["--source", str(source_home)]
        runner = CliRunner()
        assert runner.invoke(agent_config_app, [*args, "sync", harness, step]).exit_code == 0, harness
        _declare(source_home, harness, drops[harness])
        result = runner.invoke(agent_config_app, [*args, "sync", harness, step])
        assert result.exit_code == 0, f"{harness}: {result.output}"
        installed = (isolated_home / target).read_text()
        assert "extra" not in installed, harness
        assert "shared" in installed or '"shared"' in installed or "model" in installed, harness


def test_edited_dropped_key_kept_warned_and_released(source_home: Path, isolated_home: Path) -> None:
    """S2/S3: edited extra survives with one warned run, then silence."""
    _declare(source_home, "agy", '{"model": "shared", "extra": 1}')
    args = ["--source", str(source_home)]
    runner = CliRunner()
    assert runner.invoke(agent_config_app, [*args, "sync", "agy", "settings"]).exit_code == 0
    target = isolated_home / ".gemini/antigravity-cli/settings.json"
    installed = json.loads(target.read_text())
    installed["extra"] = 99
    target.write_text(json.dumps(installed))
    _declare(source_home, "agy", '{"model": "shared"}')
    result = runner.invoke(agent_config_app, [*args, "sync", "agy", "settings"])
    assert result.exit_code == 1, result.output
    assert "warned" in result.output and "extra" in result.output
    assert json.loads(target.read_text())["extra"] == 99
    result = runner.invoke(agent_config_app, [*args, "sync", "agy", "settings"])
    assert result.exit_code == 0, result.output
    assert json.loads(target.read_text())["extra"] == 99
    assert "extra" not in result.output


def test_nested_drop_removes_only_the_dropped_leaf(source_home: Path, isolated_home: Path) -> None:
    """S4: dropping permissions.defaultMode keeps permissions.allow and the local permissions.local."""
    (source_home / "harnesses/claude/settings.json").write_text(
        json.dumps({"permissions": {"defaultMode": "default", "allow": ["Bash(git status*)"]}})
    )
    args = ["--source", str(source_home)]
    runner = CliRunner()
    assert runner.invoke(agent_config_app, [*args, "sync", "claude", "config"]).exit_code == 0
    target = isolated_home / ".claude/settings.json"
    installed = json.loads(target.read_text())
    installed["permissions"]["local"] = "keep"
    target.write_text(json.dumps(installed))
    (source_home / "harnesses/claude/settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(git status*)"]}})
    )
    result = runner.invoke(agent_config_app, [*args, "sync", "claude", "config"])
    assert result.exit_code == 0, result.output
    permissions = json.loads(target.read_text())["permissions"]
    assert "defaultMode" not in permissions
    assert permissions["allow"] == ["Bash(git status*)"]
    assert permissions["local"] == "keep"


def test_empty_parent_pruned_after_leaf_removal(source_home: Path, isolated_home: Path) -> None:
    """S5: dropping the only leaf of a: {b: 1} removes a entirely."""
    _declare(source_home, "agy", '{"a": {"b": 1}}')
    args = ["--source", str(source_home)]
    runner = CliRunner()
    assert runner.invoke(agent_config_app, [*args, "sync", "agy", "settings"]).exit_code == 0
    _declare(source_home, "agy", "{}")
    result = runner.invoke(agent_config_app, [*args, "sync", "agy", "settings"])
    assert result.exit_code == 0, result.output
    assert "a" not in json.loads((isolated_home / ".gemini/antigravity-cli/settings.json").read_text())


def test_type_aware_compare_treats_true_vs_one_as_edited(source_home: Path, isolated_home: Path) -> None:
    """S6: recorded true, installed 1 -> edited -> kept and warned."""
    _declare(source_home, "agy", '{"flag": true}')
    args = ["--source", str(source_home)]
    runner = CliRunner()
    assert runner.invoke(agent_config_app, [*args, "sync", "agy", "settings"]).exit_code == 0
    target = isolated_home / ".gemini/antigravity-cli/settings.json"
    target.write_text('{"flag": 1}')
    _declare(source_home, "agy", "{}")
    result = runner.invoke(agent_config_app, [*args, "sync", "agy", "settings"])
    assert result.exit_code == 1
    assert json.loads(target.read_text())["flag"] == 1


def test_record_refreshed_on_declared_value_change(source_home: Path, isolated_home: Path) -> None:
    """S7: extra 1 -> 2 (synced) then dropped with 2 installed -> removed."""
    _declare(source_home, "agy", '{"extra": 1}')
    args = ["--source", str(source_home)]
    runner = CliRunner()
    assert runner.invoke(agent_config_app, [*args, "sync", "agy", "settings"]).exit_code == 0
    _declare(source_home, "agy", '{"extra": 2}')
    assert runner.invoke(agent_config_app, [*args, "sync", "agy", "settings"]).exit_code == 0
    _declare(source_home, "agy", "{}")
    result = runner.invoke(agent_config_app, [*args, "sync", "agy", "settings"])
    assert result.exit_code == 0, result.output
    assert "extra" not in (isolated_home / ".gemini/antigravity-cli/settings.json").read_text()


def test_declared_arrays_and_scalars_replace(source_home: Path, isolated_home: Path) -> None:
    """S12/REQ-SYNC-13: arrays and scalars replace wholesale; null installs as null."""
    _declare(source_home, "agy", '{"list": [1, 2], "model": "shared", "n": null}')
    args = ["--source", str(source_home)]
    runner = CliRunner()
    assert runner.invoke(agent_config_app, [*args, "sync", "agy", "settings"]).exit_code == 0
    target = isolated_home / ".gemini/antigravity-cli/settings.json"
    installed = json.loads(target.read_text())
    installed["list"] = [9]
    installed["model"] = "local"
    target.write_text(json.dumps(installed))
    result = runner.invoke(agent_config_app, [*args, "sync", "agy", "settings"])
    assert result.exit_code == 0, result.output
    assert json.loads(target.read_text()) == {"list": [1, 2], "model": "shared", "n": None}


def test_migrating_legacy_key_stays_untracked(source_home: Path, isolated_home: Path) -> None:
    """S11: a jsonc-migrated localOnly key is never recorded, so a later sync keeps it."""
    (source_home / "harnesses/opencode/opencode.json").write_text('{"model": "shared"}')
    target = isolated_home / ".config/opencode/opencode.json"
    target.parent.mkdir(parents=True)
    legacy = target.with_suffix(".jsonc")
    legacy.write_text('{"localOnly": "keep-me"}')
    args = ["--source", str(source_home)]
    runner = CliRunner()
    first = runner.invoke(agent_config_app, [*args, "sync", "opencode", "config"])
    assert first.exit_code == 0, first.output
    assert json.loads(target.read_text())["localOnly"] == "keep-me"
    result = runner.invoke(agent_config_app, [*args, "sync", "opencode", "config"])
    assert result.exit_code == 0, result.output
    assert json.loads(target.read_text())["localOnly"] == "keep-me"


def test_untracked_key_never_removed_or_warned(source_home: Path, isolated_home: Path) -> None:
    """S8: a key no template declared under key tracking stays, silently, exit 0."""
    target = isolated_home / ".gemini" / "antigravity-cli" / "settings.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"model": "shared", "nativeOnly": "keep"}))
    result = CliRunner().invoke(
        agent_config_app, ["--source", str(source_home), "sync", "agy", "settings"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(target.read_text())["nativeOnly"] == "keep"
    assert "nativeOnly" not in result.output
