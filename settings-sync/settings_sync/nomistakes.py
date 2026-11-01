"""Sync ~/.claude config into ~/.no-mistakes (the no-mistakes git gate)."""

from pathlib import Path

import yaml

from settings_sync.actions import Action, Regenerate
from settings_sync.paths import Paths


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


def plan_nomistakes_config(paths: Paths) -> list[Action]:
    template = paths.source_dir / "harnesses/no-mistakes/config.yaml"
    if not template.is_file():
        raise ValueError(f"template not found: {template}")
    base, err = _load_yaml(template)
    if err is not None:
        raise ValueError(f"invalid template {template}: {err}")
    machine: dict = {}
    overlay = paths.overlay_dir / "no-mistakes.yaml"
    if overlay.is_file():
        machine, err = _load_yaml(overlay)
        if err is not None:
            raise ValueError(f"invalid overlay {overlay}: {err}")
    content = yaml.safe_dump(merge_yaml(base, machine), sort_keys=False)
    return [Regenerate(path=paths.target("nomistakes") / "config.yaml", content=content)]
