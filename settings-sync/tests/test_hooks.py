from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
from pathlib import Path

import pytest

from settings_sync.claude import sync_claude_config
from settings_sync.hooks import sync_command_hooks, sync_hook_config
from settings_sync.paths import Paths
from settings_sync.sync import Status


def group(command: str) -> dict[str, object]:
    return {"matcher": "Bash", "hooks": [{"type": "command", "command": command}]}


def test_claude_preserves_foreign_hooks_on_update_and_removal(
    source_home: Path, isolated_home: Path
) -> None:
    target = isolated_home / ".claude/settings.json"
    target.parent.mkdir()
    foreign = group("local-policy")
    shared = group("shared-policy")
    target.write_text(json.dumps({"hooks": {"PreToolUse": [foreign]}, "native": True}))
    template = source_home / "harnesses/claude/settings.json"
    template.write_text(json.dumps({"hooks": {"PreToolUse": [shared]}}))
    paths = Paths(source_home, isolated_home / "opencode", claude_home=target.parent)
    assert sync_claude_config(paths, False).status != Status.FAILED
    assert json.loads(target.read_text())["hooks"]["PreToolUse"] == [foreign, shared]
    assert sync_claude_config(paths, False).status == Status.UNCHANGED
    updated = group("updated-policy")
    template.write_text(json.dumps({"hooks": {"PreToolUse": [updated]}}))
    sync_claude_config(paths, False)
    assert json.loads(target.read_text())["hooks"]["PreToolUse"] == [foreign, updated]
    template.write_text('{"hooks": {}}')
    sync_claude_config(paths, False)
    assert json.loads(target.read_text()) == {
        "hooks": {"PreToolUse": [foreign]},
        "native": True,
    }


def test_claude_preserves_a_locally_edited_managed_hook(
    source_home: Path, isolated_home: Path
) -> None:
    target = isolated_home / ".claude/settings.json"
    paths = Paths(source_home, isolated_home / "opencode", claude_home=target.parent)
    template = source_home / "harnesses/claude/settings.json"
    template.write_text(json.dumps({"hooks": {"PreToolUse": [group("shared")]}}))
    sync_claude_config(paths, False)
    config = json.loads(target.read_text())
    config["hooks"]["PreToolUse"][0]["matcher"] = "Read"
    target.write_text(json.dumps(config))
    before = target.read_bytes()
    assert sync_claude_config(paths, False).status == Status.FAILED
    assert target.read_bytes() == before


def test_hook_check_is_read_only(source_home: Path, isolated_home: Path) -> None:
    template = source_home / "harnesses/claude/settings.json"
    template.write_text(json.dumps({"hooks": {"PreToolUse": [group("shared")]}}))
    paths = Paths(
        source_home, isolated_home / "opencode", claude_home=isolated_home / ".claude"
    )
    assert sync_claude_config(paths, True).status == Status.WOULD_CREATE
    assert not (isolated_home / ".claude").exists()
    assert not (isolated_home / ".local/state").exists()


@pytest.mark.parametrize("harness", ["codex", "goose", "agy"])
def test_native_hook_sync_preserves_local_state_and_runs(
    harness: str, source_home: Path, isolated_home: Path
) -> None:

    source_home = source_home.rename(
        source_home.with_name("source with spaces and 'quotes'")
    )
    paths = Paths(
        source_home,
        isolated_home / "opencode",
        codex_dir=isolated_home / "codex with spaces",
        goose_dir=isolated_home / "goose",
        agy_dir=isolated_home / "agy",
    )
    targets = {
        "codex": paths.codex_dir / "hooks.json",
        "goose": isolated_home / ".agents/plugins/agent-config-goose/hooks/hooks.json",
        "agy": paths.agy_dir / "hooks.json",
    }
    target = targets[harness]
    target.parent.mkdir(parents=True)
    foreign = {"SessionStart": [group("local-hook")]}
    key = "agent-config" if harness == "agy" else "hooks"
    target.write_text(json.dumps({key: foreign, "local": True}))
    outcomes = sync_command_hooks(paths, harness, False)
    assert all(outcome.status != Status.FAILED for outcome in outcomes)
    result = json.loads(target.read_text())
    assert result["local"] is True
    assert result[key]["SessionStart"] == foreign["SessionStart"]
    action = result[key]["PreToolUse"][0]["hooks"][0]
    payload = (
        {"toolCall": {"name": "run_command", "args": {"CommandLine": "sudo true"}}}
        if harness == "agy"
        else {
            "event" if harness == "goose" else "hook_event_name": "PreToolUse",
            "tool_name": "shell" if harness == "goose" else "Bash",
            "tool_input": {"command": "sudo true"},
        }
    )
    process = subprocess.run(
        action["command"],
        shell=True,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
    )
    assert process.returncode == 0, process.stderr
    decision = json.loads(process.stdout)
    assert decision.get(
        "decision", decision.get("hookSpecificOutput", {}).get("permissionDecision")
    ) in ("deny", "block")
    assert all(
        outcome.status == Status.UNCHANGED
        for outcome in sync_command_hooks(paths, harness, False)
    )


def test_hook_update_keeps_registration_order(
    source_home: Path, isolated_home: Path
) -> None:
    target = isolated_home / "hooks.json"
    shared = group("shared")
    local = group("local")
    sync_hook_config(target, {"hooks": {"PreToolUse": [shared]}}, False)
    target.write_text(json.dumps({"hooks": {"PreToolUse": [shared, local]}}))
    updated = group("updated")
    sync_hook_config(target, {"hooks": {"PreToolUse": [updated]}}, False)
    assert json.loads(target.read_text())["hooks"]["PreToolUse"] == [updated, local]


@pytest.mark.parametrize("contents", ["{", "[]", '{"hooks": []}'])
def test_invalid_native_config_is_preserved(contents: str, isolated_home: Path) -> None:
    target = isolated_home / "hooks.json"
    target.write_text(contents)
    assert sync_hook_config(target, {"hooks": {}}, False).status == Status.FAILED
    assert target.read_text() == contents


def test_agy_disabled_choice_is_preserved(
    source_home: Path, isolated_home: Path
) -> None:
    target = isolated_home / "agy/hooks.json"
    target.parent.mkdir()
    target.write_text('{"agent-config":{"enabled":false},"other":{"enabled":true}}')
    paths = Paths(source_home, isolated_home / "opencode", agy_dir=target.parent)
    assert sync_command_hooks(paths, "agy", False)[0].status == Status.REPLACED
    config = json.loads(target.read_text())
    assert config["agent-config"]["enabled"] is False
    assert config["other"] == {"enabled": True}


def test_hook_changes_make_restorable_backups(isolated_home: Path) -> None:
    target = isolated_home / "hooks.json"
    original = '{"local":true,"hooks":{"Stop":[]}}'
    target.write_text(original)
    sync_hook_config(target, {"hooks": {"PreToolUse": [group("shared")]}}, False)
    backups = list(
        (isolated_home / ".local/state/agent-config/backups").glob("*-hooks.json")
    )
    assert len(backups) == 1
    assert backups[0].read_text() == original


def test_corrupt_hook_ownership_preserves_configuration(isolated_home: Path) -> None:
    target = isolated_home / "hooks.json"
    desired = {"hooks": {"PreToolUse": [group("shared")]}}
    sync_hook_config(target, desired, False)
    (snapshot,) = (isolated_home / ".local/state/agent-config/hooks").glob("*.json")
    snapshot.write_text("{")
    original = target.read_bytes()
    assert sync_hook_config(target, desired, False).status == Status.FAILED
    assert target.read_bytes() == original


def test_hook_update_backs_up_ownership_for_rollback(isolated_home: Path) -> None:
    target = isolated_home / "hooks.json"
    sync_hook_config(target, {"hooks": {"PreToolUse": [group("old")]}}, False)
    state_dir = isolated_home / ".local/state/agent-config"
    (snapshot,) = (state_dir / "hooks").glob("*.json")
    original = snapshot.read_text()
    sync_hook_config(target, {"hooks": {"PreToolUse": [group("new")]}}, False)
    backups = list((state_dir / "backups").glob("*-" + snapshot.name))
    assert len(backups) == 1
    assert backups[0].read_text() == original
    target.write_text(
        '{"hooks":{"PreToolUse": [{"matcher":"Bash","hooks":[{"type":"command","command":"old"}]}]}}'
    )
    snapshot.write_text(backups[0].read_text())
    assert (
        sync_hook_config(target, {"hooks": {"PreToolUse": [group("old")]}}, True).status
        == Status.UNCHANGED
    )


def test_removal_conflicts_when_another_managed_group_was_edited(
    isolated_home: Path,
) -> None:
    target = isolated_home / "hooks.json"
    sync_hook_config(target, {"hooks": {"PreToolUse": [group("a"), group("b")]}}, False)
    edited = json.dumps({"hooks": {"PreToolUse": [group("edited a"), group("b")]}})
    target.write_text(edited)
    result = sync_hook_config(target, {"hooks": {"PreToolUse": [group("b")]}}, False)
    assert result.status == Status.FAILED
    assert target.read_text() == edited


@pytest.mark.parametrize(
    "hooks",
    [
        [],
        {"PreToolUse": [False]},
        {"PreToolUse": [{"hooks": [{"type": "command", "command": 42}]}]},
    ],
)
def test_claude_invalid_hook_template_preserves_native_config(
    hooks: object, source_home: Path, isolated_home: Path
) -> None:
    target = isolated_home / ".claude/settings.json"
    target.parent.mkdir()
    target.write_text('{"local":true}')
    template = source_home / "harnesses/claude/settings.json"
    template.write_text(json.dumps({"hooks": hooks}))
    paths = Paths(source_home, isolated_home / "opencode", claude_home=target.parent)
    assert sync_claude_config(paths, False).status == Status.FAILED
    assert target.read_text() == '{"local":true}'


def test_concurrent_hook_sync_is_idempotent(isolated_home: Path) -> None:
    target = isolated_home / "hooks.json"
    target.write_text(json.dumps({"hooks": {"PreToolUse": [group("local")]}}))
    desired = {"hooks": {"PreToolUse": [group("shared")]}}
    with ThreadPoolExecutor(max_workers=4) as executor:
        outcomes = list(
            executor.map(lambda _: sync_hook_config(target, desired, False), range(4))
        )
    assert [outcome.status for outcome in outcomes].count(Status.REPLACED) == 1
    assert all(
        outcome.status in (Status.REPLACED, Status.UNCHANGED) for outcome in outcomes
    )
    assert json.loads(target.read_text())["hooks"]["PreToolUse"] == [
        group("local"),
        group("shared"),
    ]
