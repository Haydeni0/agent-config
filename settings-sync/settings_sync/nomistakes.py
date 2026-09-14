"""Sync ~/.claude config into ~/.no-mistakes (the no-mistakes git gate)."""

from pathlib import Path

import yaml

from settings_sync.sync import Outcome, Status, sync_yaml


def merge_yaml(base: dict, overlay: dict) -> dict:
    """Deep-merge into a new dict; inputs are never mutated.

    Dict nodes merge recursively (new nested dicts - no aliasing of merged
    branches; shallow aliasing of non-dict leaves is fine because the result
    is only ever dumped). Any non-dict overlay value - scalar, list, null -
    replaces the base value entirely, as does a type change in either
    direction: no partial merge across type changes. Lists replace, never
    concatenate. An explicit `key: null` in the overlay writes null to the
    output (scalar-replace, not treat-as-absent).
    """
    merged: dict = {key: (dict(value) if isinstance(value, dict) else value) for key, value in base.items()}
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_yaml(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(path: Path) -> tuple[dict | None, str | None]:
    """Parse a YAML file into a dict; an empty file is {} not an error."""
    try:
        loaded = yaml.safe_load(path.read_text())
    except yaml.YAMLError as err:
        return None, " ".join(str(err).split())
    if loaded is None:
        return {}, None
    if not isinstance(loaded, dict):
        return None, f"top level is {type(loaded).__name__}, expected a mapping"
    return loaded, None


def sync_nomistakes_config(target: Path, template: Path, overlay: Path, dry_run: bool = False) -> Outcome:
    """Merge the tracked template + untracked machine overlay into ~/.no-mistakes/config.yaml.

    The target is fully derived, pi-style: regenerated on every sync with no
    force gate (force=True at the sync_yaml call site). Hand edits are drift
    and die on the next sync - machine-only keys belong in the overlay, never
    in the target. The overlay is optional; the template is the source of
    truth, so it missing is NO_SOURCE. Either file failing to parse leaves
    the existing target untouched.
    """
    if not template.is_file():
        return Outcome(target, Status.NO_SOURCE, f"template not found: {template}")

    base, err = _load_yaml(template)
    if err is not None:
        return Outcome(target, Status.FAILED, f"invalid template {template}: {err}")

    machine: dict = {}
    if overlay.is_file():
        machine, err = _load_yaml(overlay)
        if err is not None:
            return Outcome(target, Status.FAILED, f"invalid overlay {overlay}: {err}")

    merged = merge_yaml(base, machine)
    content = yaml.safe_dump(merged, sort_keys=False)
    return sync_yaml(target, content, force=True, dry_run=dry_run)
