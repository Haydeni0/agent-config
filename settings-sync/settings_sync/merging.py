"""Merge declared config defaults while retaining native local state."""

from collections.abc import Mapping, MutableMapping
import json
from pathlib import Path

import yaml

from settings_sync.sync import Outcome, Status, install_text


def merge_defaults(target: MutableMapping[str, object], source: Mapping[str, object]) -> None:
    for key, value in source.items():
        existing = target.get(key)
        if isinstance(existing, MutableMapping) and isinstance(value, Mapping):
            merge_defaults(existing, value)
        elif key not in target or type(existing) is not type(value) or existing != value:
            target[key] = value


def install_merged(target: Path, content: str, existing: str | None, dry_run: bool) -> Outcome:
    if content == existing:
        return Outcome(target, Status.UNCHANGED, "identical")
    if dry_run:
        return Outcome(target, Status.WOULD_CREATE if existing is None else Status.WOULD_REPLACE, "managed defaults differ", existing, content)
    return install_text(target, content, existing)


def sync_json_defaults(target: Path, content: str, dry_run: bool = False) -> Outcome:
    try:
        if target.is_symlink():
            raise ValueError("expected regular configuration file; destination is a symlink")
        defaults = json.loads(content)
        existing = target.read_text() if target.exists() else None
        config = json.loads(existing) if existing is not None else {}
        if not isinstance(defaults, dict) or not isinstance(config, dict):
            raise ValueError("configuration must be a JSON object")
        previous = json.dumps(config, sort_keys=True)
        merge_defaults(config, defaults)
        rendered = existing if existing is not None and json.dumps(config, sort_keys=True) == previous else json.dumps(config, indent=2) + "\n"
        return install_merged(target, rendered, existing, dry_run)
    except (OSError, ValueError) as exc:
        return Outcome(target, Status.FAILED, f"could not merge JSON configuration: {exc}")


def sync_yaml_defaults(target: Path, content: str, dry_run: bool = False) -> Outcome:
    try:
        if target.is_symlink():
            raise ValueError("expected regular configuration file; destination is a symlink")
        defaults = yaml.safe_load(content)
        existing = target.read_text() if target.exists() else None
        config = yaml.safe_load(existing) if existing is not None else {}
        if not isinstance(defaults, dict) or not isinstance(config, dict):
            raise ValueError("configuration must be a YAML mapping")
        previous = yaml.safe_dump(config, sort_keys=True)
        merge_defaults(config, defaults)
        rendered = existing if existing is not None and yaml.safe_dump(config, sort_keys=True) == previous else yaml.safe_dump(config, sort_keys=False)
        return install_merged(target, rendered, existing, dry_run)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return Outcome(target, Status.FAILED, f"could not merge YAML configuration: {exc}")
