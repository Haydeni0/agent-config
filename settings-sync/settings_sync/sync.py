"""Shared outcome types and symlink sync helper."""

import json
import os
import shutil
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Self

import yaml


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
    WOULD_SKIP = "would_skip"


class Outcome:
    """Result of one sync action: what happened at a path."""

    def __init__(
        self,
        path: Path,
        status: Status,
        detail: str = "",
        old_content: str | None = None,
        new_content: str | None = None,
    ) -> None:
        self.path = path
        self.status = status
        self.detail = detail
        self.old_content = old_content
        self.new_content = new_content

    @property
    def changed(self) -> bool:
        return self.status in (Status.CREATED, Status.REPLACED)

    def __repr__(self) -> str:
        return f"Outcome(path={self.path!r}, status={self.status!r}, detail={self.detail!r})"

    def __eq__(self, other: "Outcome") -> bool:  # type: ignore[override]
        return (
            isinstance(other, Outcome)
            and self.path == other.path
            and self.status == other.status
            and self.detail == other.detail
        )


def _resolve_link_target(link: Path) -> Path:
    rel = os.readlink(link)
    return (link.parent / rel).resolve()


def sync_symlink(target: Path, source: Path, force: bool = False, dry_run: bool = False) -> Outcome:
    """Create or repair a relative symlink at `target` pointing to `source`."""
    desired_rel = os.path.relpath(source, target.parent)

    if dry_run:
        if not target.exists() and not target.is_symlink():
            return Outcome(target, Status.WOULD_CREATE, f"symlink -> {desired_rel}")
        if target.is_symlink() and _resolve_link_target(target) == source.resolve():
            return Outcome(target, Status.UNCHANGED, "already correct")
        return Outcome(target, Status.WOULD_REPLACE, f"-> {desired_rel}")

    if not target.exists() and not target.is_symlink():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(desired_rel)
        return Outcome(target, Status.CREATED, f"symlink -> {desired_rel}")

    if target.is_symlink():
        if _resolve_link_target(target) == source.resolve():
            return Outcome(target, Status.UNCHANGED, "already correct")
        if not force:
            return Outcome(
                target,
                Status.WARNED,
                f"symlink points elsewhere; use --force to retarget -> {desired_rel}",
            )
        target.unlink()
        target.symlink_to(desired_rel)
        return Outcome(target, Status.REPLACED, f"retargeted -> {desired_rel}")

    if not force:
        return Outcome(
            target,
            Status.SKIPPED,
            f"real file/dir exists at {target}; use --force to replace with symlink",
        )

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    target.symlink_to(desired_rel)
    return Outcome(target, Status.REPLACED, f"replaced real entry -> {desired_rel}")


def sync_text(target: Path, content: str, force: bool = False, dry_run: bool = False) -> Outcome:
    """Write `content` to `target`, refusing to clobber a diverging file without force."""
    if dry_run:
        if not target.exists():
            return Outcome(target, Status.WOULD_CREATE, "new file", new_content=content)
        existing = target.read_text()
        if existing == content:
            return Outcome(target, Status.UNCHANGED, "identical")
        return Outcome(target, Status.WOULD_REPLACE, "differs from source", old_content=existing, new_content=content)

    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return Outcome(target, Status.CREATED, "new file", new_content=content)

    existing = target.read_text()
    if existing == content:
        return Outcome(target, Status.UNCHANGED, "identical")

    if not force:
        return Outcome(
            target,
            Status.SKIPPED,
            "differs from source; use --force to overwrite",
            old_content=existing,
            new_content=content,
        )

    target.write_text(content)
    return Outcome(target, Status.REPLACED, "overwrote diverging file", old_content=existing, new_content=content)


def sync_json(target: Path, content: str, force: bool = False, dry_run: bool = False) -> Outcome:
    """Write JSON `content` to `target`, using semantic dict comparison to avoid false-positive drift."""
    try:
        new_obj = json.loads(content)
    except json.JSONDecodeError as err:
        return Outcome(target, Status.FAILED, f"invalid JSON in source content: {err}")

    if not target.exists():
        if dry_run:
            return Outcome(target, Status.WOULD_CREATE, "new file", new_content=content)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return Outcome(target, Status.CREATED, "new file", new_content=content)

    existing_text = target.read_text()
    try:
        existing_obj = json.loads(existing_text)
        if existing_obj == new_obj:
            return Outcome(target, Status.UNCHANGED, "identical")
    except json.JSONDecodeError:
        pass

    if dry_run:
        return Outcome(target, Status.WOULD_REPLACE, "differs from source", old_content=existing_text, new_content=content)

    if not force:
        return Outcome(
            target,
            Status.SKIPPED,
            "differs from source; use --force to overwrite",
            old_content=existing_text,
            new_content=content,
        )

    target.write_text(content)
    return Outcome(target, Status.REPLACED, "overwrote diverging file", old_content=existing_text, new_content=content)


def sync_yaml(target: Path, content: str, force: bool = False, dry_run: bool = False) -> Outcome:
    """Write YAML `content` to `target`, using semantic dict comparison to avoid false-positive drift.

    Same contract as sync_json with YAML parsing: both sides are parsed and
    compared as objects, so key-order-only differences are UNCHANGED while
    any real value difference (including an unparseable existing target,
    which counts as diverging) needs `force` to overwrite.
    """
    try:
        new_obj = yaml.safe_load(content)
    except yaml.YAMLError as err:
        return Outcome(target, Status.FAILED, f"invalid YAML in source content: {err}")

    if not target.exists():
        if dry_run:
            return Outcome(target, Status.WOULD_CREATE, "new file", new_content=content)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return Outcome(target, Status.CREATED, "new file", new_content=content)

    existing_text = target.read_text()
    try:
        existing_obj = yaml.safe_load(existing_text)
        if existing_obj == new_obj:
            return Outcome(target, Status.UNCHANGED, "identical")
    except yaml.YAMLError:
        pass

    if dry_run:
        return Outcome(target, Status.WOULD_REPLACE, "differs from source", old_content=existing_text, new_content=content)

    if not force:
        return Outcome(
            target,
            Status.SKIPPED,
            "differs from source; use --force to overwrite",
            old_content=existing_text,
            new_content=content,
        )

    target.write_text(content)
    return Outcome(target, Status.REPLACED, "overwrote diverging file", old_content=existing_text, new_content=content)


def sync_dir_symlinks(
    target_dir: Path,
    source_dir: Path,
    force: bool = False,
    dry_run: bool = False,
) -> list[Outcome]:
    """Symlink each directory in source_dir into target_dir and handle orphans."""
    if not source_dir.is_dir():
        return [Outcome(target_dir, Status.NO_SOURCE, f"source dir not found: {source_dir}")]

    outcomes: list[Outcome] = []
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    source_names: set[str] = set()
    for source_sub in sorted(source_dir.iterdir(), key=lambda p: p.name):
        if not source_sub.is_dir():
            continue
        source_names.add(source_sub.name)
        target_sub = target_dir / source_sub.name
        outcomes.append(sync_symlink(target_sub, source_sub, force=force, dry_run=dry_run))

    if target_dir.is_dir():
        for target_sub in sorted(target_dir.iterdir(), key=lambda p: p.name):
            if target_sub.name not in source_names:
                if dry_run:
                    outcomes.append(Outcome(target_sub, Status.WOULD_REPLACE, "orphan (would delete)"))
                    continue
                if not force:
                    outcomes.append(Outcome(target_sub, Status.WARNED, "orphan; use --force to remove"))
                    continue
                if target_sub.is_dir() and not target_sub.is_symlink():
                    shutil.rmtree(target_sub)
                else:
                    target_sub.unlink()
                outcomes.append(Outcome(target_sub, Status.REPLACED, "deleted orphan"))

    return outcomes


def sync_dir_files(
    target_dir: Path,
    source_dir: Path,
    pattern: str = "*",
    force: bool = False,
    dry_run: bool = False,
    transform: Callable[[Path], tuple[str, list[str]]] | None = None,
    sync_fn: Callable[[Path, str, bool, bool], Outcome] = sync_text,
) -> list[Outcome]:
    """Sync files matching pattern from source_dir to target_dir with orphan cleanup."""
    outcomes: list[Outcome] = []
    if not source_dir.is_dir():
        return [Outcome(target_dir, Status.NO_SOURCE, f"source dir not found: {source_dir}")]

    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    source_names: set[str] = set()

    for source_file in sorted(source_dir.glob(pattern), key=lambda p: p.name):
        if not source_file.is_file():
            continue
        source_names.add(source_file.name)
        target_file = target_dir / source_file.name

        if transform:
            content, warnings = transform(source_file)
            for w in warnings:
                outcomes.append(Outcome(source_file, Status.WARNED, w))
        else:
            content = source_file.read_text()

        outcomes.append(sync_fn(target_file, content, force=force, dry_run=dry_run))

    if target_dir.is_dir():
        for target_file in sorted(target_dir.glob(pattern), key=lambda p: p.name):
            if target_file.name not in source_names:
                if dry_run:
                    outcomes.append(Outcome(target_file, Status.WOULD_REPLACE, "orphan (would delete)"))
                    continue
                if not force:
                    outcomes.append(Outcome(target_file, Status.WARNED, "orphan not in source; use --force to remove"))
                    continue
                target_file.unlink()
                outcomes.append(Outcome(target_file, Status.REPLACED, "deleted orphan"))

    return outcomes
