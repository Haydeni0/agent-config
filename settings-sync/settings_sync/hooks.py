"""Reconcile managed hook groups while preserving native registrations."""

import json
from pathlib import Path
import shlex
import shutil
from typing import Literal

from settings_sync.actions import Action, File, MergedConfig, Mode, Outcome, Status
from settings_sync.merging import JsonCodec
from settings_sync.ownership import OwnershipStore
from settings_sync.paths import Paths


HookGroups = dict[str, list[dict[str, object]]]


def hook_groups(value: object) -> HookGroups:
    if not isinstance(value, dict) or not all(
        isinstance(event, str)
        and isinstance(groups, list)
        and all(isinstance(group, dict) for group in groups)
        for event, groups in value.items()
    ):
        raise ValueError("hooks must map event names to lists of groups")
    for groups in value.values():
        for group in groups:
            actions = group.get("hooks", [])
            if not isinstance(actions, list) or not all(
                isinstance(action, dict) for action in actions
            ):
                raise ValueError("hook actions must be a list of objects")
            for action in actions:
                if action.get("type", "command") == "command" and not isinstance(
                    action.get("command"), str
                ):
                    raise ValueError("command hook action requires a string command")
    return value


def reconcile_hooks(
    current: HookGroups, previous: HookGroups, desired: HookGroups
) -> HookGroups:
    result = {}
    for event in dict.fromkeys((*current, *previous, *desired)):
        installed = current.get(event, [])
        owned = previous.get(event, [])
        wanted = desired.get(event, [])
        if any(group not in installed for group in owned):
            raise ValueError(
                f"managed {event} hook changed locally; reconcile it with the ownership snapshot before syncing"
            )
        groups = []
        inserted = False
        for group in installed:
            if group in owned:
                if not inserted:
                    groups.extend(
                        item
                        for item in wanted
                        if item not in installed or item in owned
                    )
                    inserted = True
            else:
                groups.append(group)
        groups.extend(group for group in wanted if group not in groups)
        if groups:
            result[event] = groups
    return result


COMMAND_PLACEHOLDER = "${AGENT_CONFIG_COMMAND}"
CommandHarness = Literal["claude", "codex", "goose", "agy"]


def has_command_placeholder(groups: HookGroups) -> bool:
    return any(
        COMMAND_PLACEHOLDER in hook.get("command", "")
        for event_groups in groups.values()
        for group in event_groups
        for hook in group.get("hooks", [])
    )


def expand_command_hooks(
    source_dir: Path, harness: CommandHarness, groups: HookGroups
) -> None:
    """Replace the command placeholder in every action with the quoted Node
    invocation of the checkout's entry point for `harness`.

    Raises ValueError when Node or the entry point and its policy are missing,
    so callers fail before writing a hook that could not run.
    """
    node = shutil.which("node")
    entry = source_dir / "hooks/command.mjs"
    if (
        node is None
        or not entry.is_file()
        or not (entry.parent / "core/command-policy.mjs").is_file()
    ):
        raise ValueError(
            "command hooks require Node.js, the command entry point and its shared policy in the source checkout"
        )
    invocation = shlex.join((node, str(entry), harness))
    for event_groups in groups.values():
        for group in event_groups:
            for hook in group.get("hooks", []):
                if isinstance(hook.get("command"), str):
                    hook["command"] = hook["command"].replace(
                        COMMAND_PLACEHOLDER, invocation
                    )


def plan_command_hooks(paths: Paths, harness: CommandHarness) -> list[Action]:
    directory = "gemini" if harness == "agy" else harness
    source = paths.source_dir / "harnesses" / directory / "hooks.json"
    plugin = paths.goose_plugin_dir
    target = (
        plugin / "hooks/hooks.json"
        if harness == "goose"
        else paths.target(harness) / "hooks.json"
    )
    defaults = json.loads(source.read_text())
    key = "agent-config" if harness == "agy" else "hooks"
    expand_command_hooks(paths.source_dir, harness, hook_groups(defaults[key]))
    actions: list[Action] = [MergedConfig(target, JsonCodec(), defaults, hook_key=key)]
    if harness == "goose":
        manifest = (
            json.dumps(
                {
                    "name": "agent-config-goose",
                    "version": "1.0.0",
                    "description": "Shared command policy",
                },
                indent=2,
            )
            + "\n"
        )
        actions.append(File(plugin / "plugin.json", manifest))
    return actions


def sync_command_hooks(
    paths: Paths, harness: CommandHarness, dry_run: bool
) -> list[Outcome]:
    """Interim wrapper over plan_command_hooks; dies in Task 15."""
    from settings_sync.executor import execute
    try:
        store = OwnershipStore()
        store.load(Mode.DRY_RUN if dry_run else Mode.APPLY)
        return execute(plan_command_hooks(paths, harness), Mode.DRY_RUN if dry_run else Mode.APPLY, store)
    except (OSError, ValueError) as exc:
        target = (
            paths.goose_plugin_dir / "hooks/hooks.json"
            if harness == "goose"
            else paths.target(harness) / "hooks.json"
        )
        return [Outcome(target, Status.FAILED, f"could not prepare {harness} hooks: {exc}")]
