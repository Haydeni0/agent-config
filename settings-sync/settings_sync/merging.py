"""Merge declared config defaults while retaining native local state."""

import datetime
import json
import re
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Protocol

import tomlkit
import yaml
from tomlkit.exceptions import ParseError

from settings_sync.actions import Outcome, Status
from settings_sync.sync import install_text


class Codec(Protocol):
    name: str

    def loads(self, text: str) -> Mapping[str, object]: ...

    def dumps(self, obj: Mapping[str, object]) -> str: ...


class JsonCodec:
    name = "json"

    def loads(self, text: str) -> Mapping[str, object]:
        return json.loads(text)

    def dumps(self, obj: Mapping[str, object]) -> str:
        return json.dumps(obj, indent=2) + "\n"


class YamlCodec:
    name = "yaml"

    def loads(self, text: str) -> Mapping[str, object]:
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid YAML: {exc}") from exc

    def dumps(self, obj: Mapping[str, object]) -> str:
        return yaml.safe_dump(obj, sort_keys=False)


class TomlCodec:
    name = "toml"

    def loads(self, text: str) -> Mapping[str, object]:
        try:
            return tomlkit.parse(text)
        except ParseError as exc:
            raise ValueError(f"invalid TOML: {exc}") from exc

    def dumps(self, obj: Mapping[str, object]) -> str:
        return tomlkit.dumps(obj)


_CODECS = {codec.name: codec for codec in (JsonCodec(), YamlCodec(), TomlCodec())}


def codec_by_name(name: str) -> Codec:
    if name not in _CODECS:
        raise ValueError(f"unknown config codec: {name}")
    return _CODECS[name]


_LINE_COMMENT = re.compile(r"//[^\n]*")
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def strip_jsonc(text: str) -> str:
    """Remove // line comments and trailing commas so JSONC parses as JSON."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    stripped = "".join(out)
    return _TRAILING_COMMA.sub(r"\1", stripped)


def canonicalize(value: object) -> object:
    """Map TOML-only value types onto JSON-native ones so record equality is stable."""
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: canonicalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    return value


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
