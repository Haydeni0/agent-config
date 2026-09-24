"""Read the base opencode config from ~/.claude and write the generated opencode.json."""

import json
import re
from pathlib import Path

from settings_sync.sync import Outcome, Status
from settings_sync.merging import merge_defaults, sync_json_defaults

OPENCODE_SCHEMA = "https://opencode.ai/config.json"
TUI_SCHEMA = "https://opencode.ai/tui.json"

_LINE_COMMENT = re.compile(r"//[^\n]*")
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _strip_jsonc(text: str) -> str:
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


def build_config(base_path: Path) -> dict:
    if base_path.is_file():
        config = json.loads(base_path.read_text())
    else:
        config = {}
    if not isinstance(config, dict):
        raise ValueError("configuration must be a JSON object")
    config.setdefault("$schema", OPENCODE_SCHEMA)
    return config


def sync_config(target: Path, base_path: Path, force: bool = False, dry_run: bool = False) -> Outcome:
    legacy_path = target.with_suffix(".jsonc")
    try:
        config = build_config(base_path)
        if legacy_path.is_symlink() or legacy_path.exists() and not legacy_path.is_file():
            return Outcome(target, Status.FAILED, f"legacy entry is not a regular file; preserve and resolve {legacy_path}")
        legacy_text = legacy_path.read_text() if legacy_path.is_file() else None
        if legacy_text is not None:
            legacy = json.loads(_strip_jsonc(legacy_text))
            installed = json.loads(target.read_text()) if target.exists() else {}
            if not isinstance(legacy, dict) or not isinstance(installed, dict):
                raise ValueError("legacy and installed JSON must be objects")
            conflicts = [key for key in legacy if key != "$schema" and key in installed and legacy[key] != installed[key]]
            if conflicts and not force:
                return Outcome(target, Status.SKIPPED, f"legacy config conflicts on {', '.join(conflicts)}; reconcile or use --force")
            merge_defaults(legacy, config)
            config = legacy
    except (OSError, ValueError) as err:
        return Outcome(target, Status.FAILED, f"could not prepare configuration: {err}")
    content = json.dumps(config, indent=2) + "\n"
    outcome = sync_json_defaults(target, content, dry_run=dry_run)
    if legacy_text is not None and not dry_run and outcome.status in (Status.CREATED, Status.REPLACED, Status.UNCHANGED):
        try:
            if legacy_path.is_symlink() or legacy_path.read_text() != legacy_text:
                return Outcome(target, Status.FAILED, "legacy file changed during sync; preserved, retry after reconciling")
            legacy_path.unlink()
        except OSError as exc:
            return Outcome(target, Status.FAILED, f"output installed but legacy cleanup failed: {exc}")
    return outcome


def build_tui(base_path: Path) -> dict:
    if base_path.is_file():
        config = json.loads(base_path.read_text())
    else:
        config = {}
    config.setdefault("$schema", TUI_SCHEMA)
    return config


def sync_tui(target: Path, base_path: Path, force: bool = False, dry_run: bool = False) -> Outcome:
    try:
        config = build_tui(base_path)
    except json.JSONDecodeError as err:
        return Outcome(target, Status.FAILED, f"invalid JSON in {base_path}: {err}")
    content = json.dumps(config, indent=2) + "\n"
    return sync_json_defaults(target, content, dry_run=dry_run)
