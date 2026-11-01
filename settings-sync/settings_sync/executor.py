"""One apply engine: lock, ownership, backups, atomic writes, conflict policy."""

import json
import os
import stat
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from settings_sync.actions import (
    Action, Directory, Effect, File, MergedConfig, Mode, Outcome, Probe, Prune,
    Regenerate, Report, Status, Symlink,
)
from settings_sync.hooks import hook_groups, reconcile_hooks
from settings_sync.merging import Codec, canonicalize, leaf_paths, merge_defaults, strip_jsonc
from settings_sync.ownership import ConfigRecord, KeyRecord, ManagedEntry, OwnershipStore
from settings_sync.paths import Paths
from settings_sync.fsutil import write_text_atomic

if TYPE_CHECKING:
    from settings_sync.registry import Harness

_FAILURES = (OSError, ValueError)
_MISSING = object()


def run(harnesses: tuple["Harness", ...], paths: Paths, mode: Mode, steps: tuple[str, ...] | None = None) -> list[Outcome]:
    store = OwnershipStore()
    # Validate step names BEFORE the lock so the CLI's BadParameter path never
    # depends on store state; the store load happens inside the lock below.
    if steps is not None:
        for harness in harnesses:
            if harness.destination(paths) is None:
                continue
            if set(steps) - {step.name for step in harness.steps}:
                raise ValueError(f"unknown step for {harness.name}: {steps}")
    try:
        with store.lock(mode is Mode.DRY_RUN):
            outcomes: list[Outcome] = []
            for harness in harnesses:
                if harness.destination(paths) is None:
                    continue
                selected = harness.steps if steps is None else tuple(step for step in harness.steps if step.name in steps)
                for step in selected:
                    missing = [paths.source_dir / name for name in step.required_sources
                               if not (paths.source_dir / name).exists()]
                    outcomes.extend(
                        Outcome(path, Status.FAILED, f"required source missing for {harness.name} {step.name}; restore it in the source checkout")
                        for path in missing
                    )
                    if missing:
                        continue
                    try:
                        if step.plan is not None:
                            outcomes.extend(execute(step.plan(paths), mode, store))
                        else:
                            outcomes.extend(step.run(paths, mode is Mode.FORCE, mode is Mode.DRY_RUN))
                    except (OSError, ValueError) as exc:
                        outcomes.append(Outcome(paths.source_dir, Status.FAILED, f"{harness.name} {step.name}: {exc}"))
            return outcomes
    except (OSError, ValueError) as exc:
        # Only lock-time store loading/saving reaches here: step plans are caught
        # per step above, so this is the whole-run corrupt-store failure (S20/S23).
        return [Outcome(store.path, Status.FAILED, str(exc))]


def _source_id(path: Path) -> str:
    return f"{path.parent.name}/{path.name}"


def _fingerprint(path: Path) -> str:
    if path.is_symlink():
        return str(path.readlink())
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_link_target(link: Path) -> Path:
    rel = os.readlink(link)
    return (link.parent / rel).resolve()


def _atomic_write(target: Path, content: str, existing: str | None) -> Outcome:
    """Install a complete file; fails loudly if the destination moved mid-sync (S61-S63)."""
    try:
        actual = target.read_text() if target.exists() else None
        if actual != existing:
            return Outcome(target, Status.FAILED, "destination changed during sync; retry")
        write_text_atomic(target, content)
    except OSError as exc:
        return Outcome(target, Status.FAILED, f"could not install output: {exc}")
    return Outcome(target, Status.CREATED if existing is None else Status.REPLACED, "",
                   old_content=existing, new_content=content)


def execute(actions: list[Action], mode: Mode, store: OwnershipStore) -> list[Outcome]:
    outcomes: list[Outcome] = []
    with store.lock(mode is Mode.DRY_RUN):
        for action in actions:
            try:
                if isinstance(action, File):
                    outcomes.append(_apply_file(action, mode, store))
                elif isinstance(action, Symlink):
                    outcomes.append(_apply_symlink(action, mode, store))
                elif isinstance(action, MergedConfig):
                    outcomes.extend(_apply_merged(action, mode, store))
                elif isinstance(action, Directory):
                    outcomes.append(_apply_directory(action, mode))
                elif isinstance(action, Regenerate):
                    outcomes.append(_apply_regenerate(action, mode))
                elif isinstance(action, Prune):
                    outcomes.extend(_apply_prune(action, mode, store))
                elif isinstance(action, Effect):
                    outcomes.append(_apply_effect(action, mode))
                elif isinstance(action, Probe):
                    if mode is Mode.DRY_RUN:
                        outcomes.append(action.check())
                elif isinstance(action, Report):
                    outcomes.append(Outcome(action.path, action.status, action.detail))
            except _FAILURES as exc:
                outcomes.append(Outcome(getattr(action, "path", store.path), Status.FAILED, f"{type(action).__name__} failed: {exc}"))
    return outcomes


def _record(store: OwnershipStore, path: Path, kind: str) -> None:
    entry = ManagedEntry(_source_id(path), Path(os.path.abspath(path)), _fingerprint(path))
    if kind == "file":
        store.record_file(entry)
    else:
        store.record_symlink(entry)


def _apply_file(action: File, mode: Mode, store: OwnershipStore) -> Outcome:
    path = action.path
    if path.is_symlink() or path.is_dir():
        return Outcome(path, Status.FAILED, "expected a regular file; preserve this entry and resolve its ownership")
    existing = path.read_text() if path.exists() else None
    entry = store.get(path)
    managed = entry is not None and existing is not None and _fingerprint(path) == entry.fingerprint
    conflict = existing is not None and existing != action.content and not managed
    if existing == action.content:
        if mode is not Mode.DRY_RUN and entry is None:
            _record(store, path, "file")
        return Outcome(path, Status.UNCHANGED, "identical")
    if mode is Mode.DRY_RUN:
        return Outcome(path, Status.WOULD_CREATE if existing is None else Status.WOULD_REPLACE,
                       "generated output differs", old_content=existing, new_content=action.content)
    if conflict and mode is Mode.APPLY:
        return Outcome(path, Status.SKIPPED, "unmanaged or locally edited output; use --force on this step to back up and replace",
                       existing, action.content)
    backup = store.backup(path) if conflict else None
    outcome = _atomic_write(path, action.content, existing)
    if outcome.status in (Status.CREATED, Status.REPLACED):
        if backup is not None:
            outcome.detail = f"; original backed up to {backup}"
        _record(store, path, "file")
    return outcome


def _apply_symlink(action: Symlink, mode: Mode, store: OwnershipStore) -> Outcome:
    path, source = action.path, action.source
    desired_rel = os.path.relpath(source, path.parent)
    exists = path.exists() or path.is_symlink()
    if path.is_symlink() and _resolve_link_target(path) == source.resolve():
        if mode is not Mode.DRY_RUN and store.get(path) is None:
            _record(store, path, "symlink")
        return Outcome(path, Status.UNCHANGED, "already correct")
    if path.is_dir() and not path.is_symlink():
        return Outcome(path, Status.FAILED, "real directory preserved; inventory its contents before migrating")
    entry = store.get(path)
    managed = entry is not None and path.is_symlink() and _fingerprint(path) == entry.fingerprint
    conflict = exists and (action.detail != "" or not managed)
    detail = action.detail or "existing entry differs; resolve ownership before replacing"
    if mode is Mode.DRY_RUN:
        return Outcome(path, Status.WOULD_CREATE if not exists else Status.WOULD_REPLACE, detail if conflict else f"symlink -> {desired_rel}")
    if conflict and mode is Mode.APPLY:
        return Outcome(path, Status.SKIPPED, detail)
    backup = store.backup(path) if conflict else None
    temporary = path.with_name(f".{path.name}.{uuid4().hex}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.symlink_to(desired_rel)
        temporary.replace(path)
    except OSError as exc:
        return Outcome(path, Status.FAILED, f"could not install symlink: {exc}")
    finally:
        temporary.unlink(missing_ok=True)
    outcome = Outcome(path, Status.REPLACED if exists else Status.CREATED, f"symlink -> {desired_rel}")
    if backup is not None:
        outcome.detail += f"; original backed up to {backup}"
    _record(store, path, "symlink")
    return outcome


def _apply_directory(action: Directory, mode: Mode) -> Outcome:
    path = action.path
    if path.exists() and not path.is_dir():
        return Outcome(path, Status.FAILED, f"expected a directory; found {path}")
    if not path.exists():
        if mode is Mode.DRY_RUN:
            return Outcome(path, Status.WOULD_CREATE, "directory")
        path.mkdir(parents=True, mode=action.mode)
        path.chmod(action.mode)
        return Outcome(path, Status.CREATED, "directory")
    current = stat.S_IMODE(path.stat().st_mode)
    if current == action.mode:
        return Outcome(path, Status.UNCHANGED, "directory")
    if mode is Mode.DRY_RUN:
        return Outcome(path, Status.WOULD_REPLACE, f"directory mode {current:o}; expected {action.mode:o}")
    path.chmod(action.mode)
    return Outcome(path, Status.REPLACED, f"directory mode {current:o} -> {action.mode:o}")


def _apply_regenerate(action: Regenerate, mode: Mode) -> Outcome:
    from settings_sync.merging import YamlCodec

    path = action.path
    if path.is_symlink() or path.is_dir():
        return Outcome(path, Status.FAILED, "expected a regular file")
    existing = path.read_text() if path.exists() else None
    if existing is not None:
        try:
            if YamlCodec().loads(existing) == YamlCodec().loads(action.content):
                return Outcome(path, Status.UNCHANGED, "identical")
        except ValueError:
            pass  # unparseable target is drift; Regenerate always rewrites it
    if mode is Mode.DRY_RUN:
        return Outcome(path, Status.WOULD_CREATE if existing is None else Status.WOULD_REPLACE,
                       "regenerated output differs", old_content=existing, new_content=action.content)
    return _atomic_write(path, action.content, existing)


def _apply_prune(action: Prune, mode: Mode, store: OwnershipStore) -> list[Outcome]:
    outcomes: list[Outcome] = []
    directory = Path(os.path.abspath(action.dir))
    for target, entry in list(store.files.items()) + list(store.symlinks.items()):
        if target.parent != directory or target.name in action.expected:
            continue
        if not target.exists() and not target.is_symlink():
            if mode is not Mode.DRY_RUN:
                store.forget(target)
            continue
        is_link = target.is_symlink()
        recorded_link = target in store.symlinks
        if target.is_dir() and not is_link or is_link != recorded_link or _fingerprint(target) != entry.fingerprint:
            outcomes.append(Outcome(target, Status.WARNED, "obsolete managed output has local changes; preserved"))
            continue
        if mode is Mode.DRY_RUN:
            outcomes.append(Outcome(target, Status.WOULD_REPLACE, "would remove unchanged managed output"))
            continue
        target.unlink()
        store.forget(target)
        outcomes.append(Outcome(target, Status.REPLACED, "removed unchanged managed output"))
    return outcomes


def _apply_effect(action: Effect, mode: Mode) -> Outcome:
    if not action.pending:
        return Outcome(action.path, Status.UNCHANGED, action.detail)
    if mode is Mode.DRY_RUN:
        return Outcome(action.path, Status.WOULD_CREATE, action.detail)
    try:
        action.run()
    except Exception as exc:  # the callable raises; any failure is this action's, never the run's (D10)
        return Outcome(action.path, Status.FAILED, f"{action.detail}: {exc}")
    return Outcome(action.path, Status.CREATED, action.detail)


def _apply_merged(action: MergedConfig, mode: Mode, store: OwnershipStore) -> list[Outcome]:
    path = action.path
    codec = action.codec
    if path.is_symlink() or path.is_dir():
        return [Outcome(path, Status.FAILED, "expected a regular configuration file")]
    existing_text = path.read_text() if path.exists() else None
    try:
        config: MutableMapping[str, object] = codec.loads(existing_text) if existing_text is not None else {}
        if not isinstance(config, MutableMapping):
            raise ValueError("configuration must be an object")
        declared = dict(action.keys)
        if action.hook_key is not None:
            declared = {key: value for key, value in declared.items() if key != action.hook_key}
        migrating: dict[str, object] = {}
        legacy_conflict = False
        if action.migrate is not None:
            legacy = dict(action.migrate)
            installed = config
            for key, value in legacy.items():
                if key == "$schema":
                    continue
                if key in installed and canonicalize(installed[key]) != canonicalize(value):
                    legacy_conflict = True
            migrating = {key: value for key, value in legacy.items() if key not in declared}
            for key, value in legacy.items():
                if key in declared:
                    continue  # template-declared keys keep template values
                merge_defaults(config, {key: value})
        if legacy_conflict and mode is not Mode.FORCE:
            # DRY_RUN previews the conflict; APPLY skips it; FORCE falls through to backup + merge (S30)
            return [Outcome(path, Status.SKIPPED, "legacy config conflicts; reconcile or use --force",
                            old_content=existing_text)]
        changed = _merge_declared(config, declared)
        removed, warned, forced_removal = _drop_undeclared(config, declared, store, path, mode)
        hooks_backup = False
        if action.hook_key is not None:
            desired_groups = hook_groups(action.keys.get(action.hook_key, {}))
            current = config.get(action.hook_key, {})
            enabled: dict[str, object] = {}
            if action.hook_key == "agent-config" and isinstance(current, dict) and "enabled" in current:
                if not isinstance(current["enabled"], bool):
                    return [Outcome(path, Status.FAILED, "hook enabled flag must be boolean")]
                enabled = {"enabled": current["enabled"]}
                current = {key: value for key, value in current.items() if key != "enabled"}
            reconciled = reconcile_hooks(hook_groups(current), store.hooks_of(path), desired_groups)
            if action.hook_key in config or action.hook_key in action.keys:
                config[action.hook_key] = {**enabled, **reconciled}
            hooks_backup = True
        if migrating:
            merge_defaults(config, migrating)
        rendered = codec.dumps(config)
        if existing_text is not None and not changed and _semantically_equal(codec, existing_text, rendered):
            rendered = existing_text
        if rendered == existing_text:
            if mode is not Mode.DRY_RUN:
                _record_config(store, path, codec, action, config)
            if warned and mode is not Mode.FORCE:
                return [Outcome(path, Status.UNCHANGED, "identical"), *_drop_warnings(path, warned)]
            return [Outcome(path, Status.UNCHANGED, "identical")]
        if mode is Mode.DRY_RUN:
            outcomes = [Outcome(path, Status.WOULD_MERGE if existing_text is not None else Status.WOULD_CREATE,
                                _merge_detail(changed, removed), old_content=existing_text, new_content=rendered)]
            outcomes.extend(_drop_warnings(path, warned))
            return outcomes
        if legacy_conflict or forced_removal or (hooks_backup and existing_text is not None):
            store.backup(path)
        outcome = _atomic_write(path, rendered, existing_text)
        if outcome.status in (Status.CREATED, Status.REPLACED, Status.UNCHANGED):
            outcome.status = Status.MERGED
            outcome.detail = _merge_detail(changed, removed)
            if mode is not Mode.DRY_RUN:
                _record_config(store, path, codec, action, config)
        if outcome.status in (Status.CREATED, Status.REPLACED, Status.MERGED, Status.UNCHANGED) and action.remove_after is not None:
            failed = _remove_after(action.remove_after, mode, action.migrate, store)
            if failed is not None:
                outcome = failed
        return [outcome] if not warned or mode is Mode.FORCE else [outcome, *_drop_warnings(path, warned)]
    except (OSError, ValueError) as exc:
        return [Outcome(path, Status.FAILED, f"could not merge configuration: {exc}")]


def _merge_declared(config: dict[str, object], declared: dict[str, object]) -> list[str]:
    before = _flat(config)
    merge_defaults(config, declared)
    after = _flat(config)
    changed = [name for name, value in after.items() if before.get(name, _MISSING) != value]
    changed.extend(name for name in before if name not in after)
    return sorted(set(changed))


def _flat(mapping: Mapping[str, object], prefix: str = "") -> dict[str, object]:
    flat: dict[str, object] = {}
    for key, value in mapping.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flat(value, name))
        else:
            flat[name] = canonicalize(value)
    return flat


def _merge_detail(changed: list[str], removed: list[str]) -> str:
    parts = []
    if changed:
        parts.append("changed: " + ", ".join(sorted(changed)))
    if removed:
        parts.append("removed: " + ", ".join(sorted(removed)))
    return "; ".join(parts)


def _semantically_equal(codec: Codec, left: str, right: str) -> bool:
    try:
        return codec.loads(left) == codec.loads(right)
    except ValueError:
        return False


def _record_config(store: OwnershipStore, path: Path, codec: Codec, action: MergedConfig, config: MutableMapping[str, object]) -> None:
    declared = {key: value for key, value in action.keys.items() if key != action.hook_key}
    records: list[KeyRecord] = []
    for leaf in sorted(leaf_paths(declared)):
        value = _leaf_value(config, leaf)
        if value is _MISSING:
            continue
        records.append(KeyRecord(leaf, value))
    hooks = hook_groups(action.keys.get(action.hook_key, {})) if action.hook_key is not None else None
    store.record_config(ConfigRecord(Path(os.path.abspath(path)), codec.name, tuple(records), hooks))


def _leaf_value(config: Mapping[str, object], leaf: tuple[str, ...]) -> object:
    node: object = config
    for segment in leaf:
        if not isinstance(node, Mapping) or segment not in node:
            return _MISSING
        node = node[segment]
    if not isinstance(node, bool):  # int(True) would erase the bool type (S6)
        for plain in (int, float, str, list, dict):
            # tomlkit wraps scalars in subclasses of the builtins; records must
            # compare type-stable across the JSON round-trip, so normalize them.
            if isinstance(node, plain) and type(node) is not plain:
                node = plain(node)
                break
    return canonicalize(node)


def _drop_undeclared(
    config: MutableMapping[str, object],
    declared: Mapping[str, object],
    store: OwnershipStore,
    path: Path,
    mode: Mode,
) -> tuple[list[str], list[str], bool]:
    """D19 remove-vs-keep: returns (removed dotted paths, warned dotted paths, force removed an edited key)."""
    declared_leaves = leaf_paths(declared)
    record = store.configs.get(Path(os.path.abspath(path)))
    removed: list[str] = []
    warned: list[str] = []
    forced = False
    if record is None:
        return removed, warned, forced
    for key_record in record.keys:
        if key_record.path in declared_leaves:
            continue
        installed = _leaf_value(config, key_record.path)
        if installed is _MISSING:
            continue
        dotted = ".".join(key_record.path)
        unchanged = type(installed) is type(key_record.value) and installed == key_record.value
        if unchanged:
            _remove_leaf(config, key_record.path, declared_leaves)
            removed.append(dotted)
        elif mode is Mode.FORCE:
            _remove_leaf(config, key_record.path, declared_leaves)
            removed.append(dotted)
            forced = True
        else:
            warned.append(dotted)
    return removed, warned, forced


def _remove_leaf(config: MutableMapping[str, object], leaf: tuple[str, ...], declared_leaves: set[tuple[str, ...]]) -> None:
    node: object = config
    for segment in leaf[:-1]:
        if not isinstance(node, Mapping) or segment not in node:
            return
        node = node[segment]
    if isinstance(node, MutableMapping):
        node.pop(leaf[-1], None)
    for depth in range(len(leaf) - 1, 0, -1):
        parent_path = leaf[:depth]
        parent: object = config
        for segment in parent_path[:-1]:
            if not isinstance(parent, Mapping) or segment not in parent:
                return
            parent = parent[segment]
        if not isinstance(parent, Mapping) or parent_path[-1] not in parent:
            return
        child = parent[parent_path[-1]]
        if isinstance(child, dict) and not child and not any(
            declared_leaf[:depth] == parent_path for declared_leaf in declared_leaves
        ):
            del parent[parent_path[-1]]
        else:
            return


def _drop_warnings(path: Path, warned: list[str]) -> list[Outcome]:
    return [
        Outcome(path, Status.WARNED,
                f"template dropped locally-edited key: {dotted}; kept and released to local state")
        for dotted in warned
    ]


def _remove_after(legacy: Path, mode: Mode, migrate: Mapping[str, object] | None, store: OwnershipStore) -> Outcome | None:
    if mode is Mode.DRY_RUN:
        return None
    try:
        if legacy.is_symlink() or legacy.exists() and not legacy.is_file():
            return Outcome(legacy, Status.FAILED, f"legacy entry is not a regular file; preserve and resolve {legacy}")
        if not legacy.exists():
            return None
        if json.loads(strip_jsonc(legacy.read_text())) != migrate:
            return Outcome(legacy, Status.FAILED, "legacy file changed during sync; preserved, retry after reconciling")
        store.backup(legacy)
        legacy.unlink()
    except (OSError, ValueError) as exc:
        return Outcome(legacy, Status.FAILED, f"output installed but legacy cleanup failed: {exc}")
    return None
