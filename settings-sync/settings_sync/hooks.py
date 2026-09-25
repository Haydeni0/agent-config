"""Reconcile managed hook groups while preserving native registrations."""

import hashlib
import json
from pathlib import Path
import shlex
import shutil
from typing import Literal

from settings_sync.merging import install_merged, merge_defaults
from settings_sync.ownership import OwnershipStore, sync_generated_json
from settings_sync.paths import Paths, state_home
from settings_sync.sync import Outcome, Status, write_text_atomic


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


def sync_hook_config(
    target: Path, defaults: dict[str, object], dry_run: bool, hook_key: str = "hooks"
) -> Outcome:
    """Merge defaults and update only hook groups adopted by this checkout."""
    try:
        store = OwnershipStore()
        with store.lock(dry_run):
            if target.is_symlink():
                raise ValueError(
                    "expected a regular hook configuration, found a symlink"
                )
            existing = target.read_text() if target.exists() else None
            config = json.loads(existing) if existing is not None else {}
            if not isinstance(config, dict):
                raise ValueError("hook configuration must be an object")
            destination = str(target.absolute())
            snapshot = (
                state_home()
                / "hooks"
                / (hashlib.sha256(destination.encode()).hexdigest() + ".json")
            )
            state = (
                json.loads(snapshot.read_text())
                if snapshot.exists()
                else {"version": 1, "target": destination, "hooks": {}}
            )
            if (
                not isinstance(state, dict)
                or state.get("version") != 1
                or state.get("target") != destination
            ):
                raise ValueError(
                    "invalid hook ownership snapshot; restore it before syncing"
                )
            desired = hook_groups(defaults.get(hook_key, {}))
            current = config.get(hook_key, {})
            enabled = {}
            if (
                hook_key == "agent-config"
                and isinstance(current, dict)
                and "enabled" in current
            ):
                if not isinstance(current["enabled"], bool):
                    raise ValueError("hook enabled flag must be boolean")
                enabled = {"enabled": current["enabled"]}
                current = {
                    key: value for key, value in current.items() if key != "enabled"
                }
            reconciled = reconcile_hooks(
                hook_groups(current), hook_groups(state.get("hooks")), desired
            )
            before = json.dumps(config, sort_keys=True)
            merge_defaults(
                config,
                {key: value for key, value in defaults.items() if key != hook_key},
            )
            if hook_key in config or hook_key in defaults:
                config[hook_key] = {**enabled, **reconciled}
            content = (
                existing
                if existing is not None and json.dumps(config, sort_keys=True) == before
                else json.dumps(config, indent=2) + "\n"
            )
            if not dry_run and snapshot.exists() and state["hooks"] != desired:
                store.backup(snapshot)
            backup = (
                store.backup(target)
                if not dry_run and existing is not None and content != existing
                else None
            )
            outcome = install_merged(target, content, existing, dry_run)
            if backup is not None:
                outcome.detail += f"; backup: {backup}"
            if not dry_run and outcome.status in (
                Status.CREATED,
                Status.REPLACED,
                Status.UNCHANGED,
            ):
                state = {"version": 1, "target": destination, "hooks": desired}
                rendered = json.dumps(state, indent=2) + "\n"
                if not snapshot.exists() or snapshot.read_text() != rendered:
                    write_text_atomic(snapshot, rendered)
            return outcome
    except (OSError, ValueError) as exc:
        return Outcome(target, Status.FAILED, f"could not sync hooks: {exc}")


def sync_command_hooks(
    paths: Paths, harness: Literal["codex", "goose", "agy"], dry_run: bool
) -> list[Outcome]:
    directory = "gemini" if harness == "agy" else harness
    source = paths.source_dir / "harnesses" / directory / "hooks.json"
    plugin = Path.home() / ".agents/plugins/agent-config-goose"
    target = (
        plugin / "hooks/hooks.json"
        if harness == "goose"
        else paths.target(harness) / "hooks.json"
    )
    try:
        node = shutil.which("node")
        entry = paths.source_dir / "hooks/command.mjs"
        if (
            node is None
            or not entry.is_file()
            or not (entry.parent / "core/command-policy.mjs").is_file()
        ):
            raise ValueError(
                "command hooks require Node.js, the command entry point and its shared policy in the source checkout"
            )
        defaults = json.loads(source.read_text())
        key = "agent-config" if harness == "agy" else "hooks"
        for groups in hook_groups(defaults[key]).values():
            for group in groups:
                for hook in group["hooks"]:
                    hook["command"] = hook["command"].replace(
                        "${AGENT_CONFIG_COMMAND}",
                        shlex.join((node, str(entry), harness)),
                    )
        outcome = sync_hook_config(target, defaults, dry_run, key)
        if harness != "goose" or outcome.status == Status.FAILED:
            return [outcome]
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
        return [
            outcome,
            sync_generated_json(plugin / "plugin.json", manifest, dry_run=dry_run),
        ]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [
            Outcome(target, Status.FAILED, f"could not prepare {harness} hooks: {exc}")
        ]
