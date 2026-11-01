"""Outcome and Status types shared by every sync layer; imports nothing internal."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from settings_sync.merging import Codec


class Status(StrEnum):
    CREATED = "created"
    REPLACED = "replaced"
    UNCHANGED = "unchanged"
    SKIPPED = "skipped"
    NO_SOURCE = "no_source"
    FAILED = "failed"
    WARNED = "warned"
    WOULD_CREATE = "would_create"
    WOULD_REPLACE = "would_replace"
    MERGED = "merged"
    WOULD_MERGE = "would_merge"


@dataclass(slots=True)
class Outcome:
    """Result of one sync action: what happened at a path."""

    path: Path
    status: Status
    detail: str = ""
    old_content: str | None = None
    new_content: str | None = None


class Action:
    """Marker base; carries no fields."""


@dataclass(frozen=True, slots=True)
class File(Action):
    path: Path
    content: str  # complete rendered file body


@dataclass(frozen=True, slots=True)
class Symlink(Action):
    path: Path  # the link location
    source: Path  # what it must point at
    detail: str = ""  # conflict guidance carried into skip/would_replace messages


@dataclass(frozen=True, slots=True)
class MergedConfig(Action):
    path: Path
    codec: "Codec"  # string annotation; TYPE_CHECKING-only import from merging
    keys: Mapping[str, object]  # template-declared keys (owned), including the hook_key subtree
    hook_key: str | None = None
    migrate: Mapping[str, object] | None = None
    remove_after: Path | None = None


@dataclass(frozen=True, slots=True)
class Directory(Action):
    path: Path
    mode: int


@dataclass(frozen=True, slots=True)
class Regenerate(Action):
    path: Path
    content: str


@dataclass(frozen=True, slots=True)
class Prune(Action):
    dir: Path
    expected: frozenset[str]


@dataclass(frozen=True, slots=True)
class Effect(Action):
    path: Path
    pending: bool
    detail: str
    run: Callable[[], None]  # raises on failure; never writes configs


@dataclass(frozen=True, slots=True)
class Probe(Action):
    path: Path
    check: Callable[[], Outcome]  # runs only in DRY_RUN


@dataclass(frozen=True, slots=True)
class Report(Action):
    path: Path
    status: Status
    detail: str
