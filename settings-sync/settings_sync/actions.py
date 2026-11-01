"""Outcome and Status types shared by every sync layer; imports nothing internal."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


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


@dataclass(slots=True)
class Outcome:
    """Result of one sync action: what happened at a path."""

    path: Path
    status: Status
    detail: str = ""
    old_content: str | None = None
    new_content: str | None = None
