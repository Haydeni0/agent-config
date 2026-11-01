from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
from pathlib import Path

import pytest

from settings_sync.actions import Mode, Outcome, Status
from settings_sync.claude import plan_claude_config
from settings_sync.executor import execute
from settings_sync.hooks import plan_command_hooks
from settings_sync.merging import JsonCodec
from settings_sync.actions import MergedConfig
from settings_sync.ownership import OwnershipStore
from settings_sync.paths import Paths


def group(command: str) -> dict[str, object]:
    return {"matcher": "Bash", "hooks": [{"type": "command", "command": command}]}


def apply_claude_config(paths: Paths, mode: Mode) -> list[Outcome]:
    store = OwnershipStore()
    store.load(mode)
    return execute(plan_claude_config(paths), mode, store)


def apply_hook_config(target: Path, desired: dict, mode: Mode, hook_key: str = "hooks") -> Outcome:
    store = OwnershipStore()
    store.load(mode)
    return execute([MergedConfig(target, JsonCodec(), desired, hook_key=hook_key)], mode, store)[0]


def _apply_hooks(paths: Paths, harness: str, mode: Mode = Mode.APPLY) -> list[Outcome]:
    from settings_sync.registry import select_harnesses
    spec = select_harnesses(harness)[0].hooks
    store = OwnershipStore()
    store.load(mode)
    return execute(plan_command_hooks(paths, harness, spec), mode, store)


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
    assert apply_claude_config(paths, Mode.APPLY)[0].status != Status.FAILED
    assert json.loads(target.read_text())["hooks"]["PreToolUse"] == [foreign, shared]
    assert apply_claude_config(paths, Mode.APPLY)[0].status == Status.UNCHANGED
    updated = group("updated-policy")
    template.write_text(json.dumps({"hooks": {"PreToolUse": [updated]}}))
    apply_claude_config(paths, Mode.APPLY)
    assert json.loads(target.read_text())["hooks"]["PreToolUse"] == [foreign, updated]
    template.write_text('{"hooks": {}}')
    apply_claude_config(paths, Mode.APPLY)
    assert json.loads(target.read_text()) == {
        "hooks": {"PreToolUse": [foreign]},
        "native": True,
    }


@pytest.mark.parametrize("mode", [Mode.APPLY, Mode.FORCE])
def test_claude_preserves_a_locally_edited_managed_hook(
    source_home: Path, isolated_home: Path, mode: Mode
) -> None:
    target = isolated_home / ".claude/settings.json"
    paths = Paths(source_home, isolated_home / "opencode", claude_home=target.parent)
    template = source_home / "harnesses/claude/settings.json"
    template.write_text(json.dumps({"hooks": {"PreToolUse": [group("shared")]}}))
    apply_claude_config(paths, Mode.APPLY)
    config = json.loads(target.read_text())
    config["hooks"]["PreToolUse"][0]["matcher"] = "Read"
    target.write_text(json.dumps(config))
    before = target.read_bytes()
    assert apply_claude_config(paths, mode)[0].status == Status.FAILED
    assert target.read_bytes() == before


def test_hook_check_is_read_only(source_home: Path, isolated_home: Path) -> None:
    template = source_home / "harnesses/claude/settings.json"
    template.write_text(json.dumps({"hooks": {"PreToolUse": [group("shared")]}}))
    paths = Paths(
        source_home, isolated_home / "opencode", claude_home=isolated_home / ".claude"
    )
    assert apply_claude_config(paths, Mode.DRY_RUN)[0].status == Status.WOULD_CREATE
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
    outcomes = _apply_hooks(paths, harness)
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
        for outcome in _apply_hooks(paths, harness)
    )


def test_hook_update_keeps_registration_order(
    source_home: Path, isolated_home: Path
) -> None:
    target = isolated_home / "hooks.json"
    shared = group("shared")
    local = group("local")
    apply_hook_config(target, {"hooks": {"PreToolUse": [shared]}}, Mode.APPLY)
    target.write_text(json.dumps({"hooks": {"PreToolUse": [shared, local]}}))
    updated = group("updated")
    apply_hook_config(target, {"hooks": {"PreToolUse": [updated]}}, Mode.APPLY)
    assert json.loads(target.read_text())["hooks"]["PreToolUse"] == [updated, local]


@pytest.mark.parametrize("contents", ["{", "[]", '{"hooks": []}'])
def test_invalid_native_config_is_preserved(contents: str, isolated_home: Path) -> None:
    target = isolated_home / "hooks.json"
    target.write_text(contents)
    assert apply_hook_config(target, {"hooks": {}}, Mode.APPLY).status == Status.FAILED
    assert target.read_text() == contents


def test_agy_disabled_choice_is_preserved(
    source_home: Path, isolated_home: Path
) -> None:
    target = isolated_home / "agy/hooks.json"
    target.parent.mkdir()
    target.write_text('{"agent-config":{"enabled":false},"other":{"enabled":true}}')
    paths = Paths(source_home, isolated_home / "opencode", agy_dir=target.parent)
    assert _apply_hooks(paths, "agy")[0].status == Status.MERGED
    config = json.loads(target.read_text())
    assert config["agent-config"]["enabled"] is False
    assert config["other"] == {"enabled": True}


def test_hook_changes_make_restorable_backups(isolated_home: Path) -> None:
    target = isolated_home / "hooks.json"
    original = '{"local":true,"hooks":{"Stop":[]}}'
    target.write_text(original)
    apply_hook_config(target, {"hooks": {"PreToolUse": [group("shared")]}}, Mode.APPLY)
    backups = list(
        (isolated_home / ".local/state/agent-config/backups").glob("*-hooks.json")
    )
    assert len(backups) == 1
    assert backups[0].read_text() == original


def test_corrupt_hook_ownership_preserves_configuration(isolated_home: Path) -> None:
    target = isolated_home / "hooks.json"
    desired = {"hooks": {"PreToolUse": [group("shared")]}}
    apply_hook_config(target, desired, Mode.APPLY)
    store = isolated_home / ".local/state/agent-config/managed.json"
    store.write_text("{")
    original = target.read_bytes()
    # A corrupt store fails the whole run before any action (S20/S23); only
    # executor.run converts that to an outcome, so the helper raises here.
    with pytest.raises(ValueError):
        apply_hook_config(target, desired, Mode.APPLY)
    assert target.read_bytes() == original


def test_hook_update_backs_up_ownership_for_rollback(isolated_home: Path) -> None:
    target = isolated_home / "hooks.json"
    apply_hook_config(target, {"hooks": {"PreToolUse": [group("old")]}}, Mode.APPLY)
    state_dir = isolated_home / ".local/state/agent-config"
    store = state_dir / "managed.json"
    original = store.read_bytes()
    apply_hook_config(target, {"hooks": {"PreToolUse": [group("new")]}}, Mode.APPLY)
    backups = [p for p in (state_dir / "backups").glob("*") if p.name.endswith(".json") and p.is_file()]
    assert any(backup.read_bytes() == original for backup in backups), sorted(p.name for p in backups)
    assert json.loads(store.read_text())["configs"]


def test_removal_conflicts_when_another_managed_group_was_edited(
    isolated_home: Path,
) -> None:
    target = isolated_home / "hooks.json"
    apply_hook_config(target, {"hooks": {"PreToolUse": [group("a"), group("b")]}}, Mode.APPLY)
    edited = json.dumps({"hooks": {"PreToolUse": [group("edited a"), group("b")]}})
    target.write_text(edited)
    result = apply_hook_config(target, {"hooks": {"PreToolUse": [group("b")]}}, Mode.APPLY)
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
    with pytest.raises(ValueError):
        plan_claude_config(paths)
    assert target.read_text() == '{"local":true}'


def test_concurrent_hook_sync_is_idempotent(isolated_home: Path) -> None:
    target = isolated_home / "hooks.json"
    target.write_text(json.dumps({"hooks": {"PreToolUse": [group("local")]}}))
    desired = {"hooks": {"PreToolUse": [group("shared")]}}
    with ThreadPoolExecutor(max_workers=4) as executor:
        outcomes = list(
            executor.map(lambda _: apply_hook_config(target, desired, Mode.APPLY), range(4))
        )
    assert [outcome.status for outcome in outcomes].count(Status.MERGED) == 1
    assert all(
        outcome.status in (Status.MERGED, Status.UNCHANGED) for outcome in outcomes
    )
    assert json.loads(target.read_text())["hooks"]["PreToolUse"] == [
        group("local"),
        group("shared"),
    ]


def test_claude_sync_installs_the_mailbox_stop_guard_alongside_the_wt_marker(
    source_home: Path, isolated_home: Path
) -> None:
    # the Stop registration as shipped: the wt statusline marker stays, and a
    # second group blocks turn ends on unread mesh mail
    target = isolated_home / ".claude/settings.json"
    paths = Paths(source_home, isolated_home / "opencode", claude_home=target.parent)
    template = source_home / "harnesses/claude/settings.json"
    template.write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": 'bash "$HOME/.claude/custom/plugins/worktrunk/hooks/wt.sh" '
                                    '-C "$CLAUDE_PROJECT_DIR" config state marker set x || true',
                                }
                            ]
                        },
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": 'node "$HOME/.claude/hooks/mailbox-guard.mjs" claude',
                                    "timeout": 20,
                                }
                            ]
                        },
                    ]
                }
            }
        )
    )

    assert apply_claude_config(paths, Mode.APPLY)[0].status != Status.FAILED

    stop = json.loads(target.read_text())["hooks"]["Stop"]
    assert len(stop) == 2
    assert "mailbox-guard.mjs" in stop[1]["hooks"][0]["command"]
    assert stop[1]["hooks"][0]["timeout"] == 20
    assert "wt.sh" in stop[0]["hooks"][0]["command"]
    assert apply_claude_config(paths, Mode.APPLY)[0].status == Status.UNCHANGED
