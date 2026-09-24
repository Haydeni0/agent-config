"""Shared outcome types and symlink sync helper."""

import json
import os
import stat
import tempfile
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

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
    exists = target.exists() or target.is_symlink()
    if target.is_symlink() and _resolve_link_target(target) == source.resolve():
        return Outcome(target, Status.UNCHANGED, "already correct")
    if target.is_dir() and not target.is_symlink():
        return Outcome(target, Status.SKIPPED, "real directory preserved; inventory it before migrating")
    if dry_run:
        return Outcome(target, Status.WOULD_REPLACE if exists else Status.WOULD_CREATE, f"symlink -> {desired_rel}")
    if exists and not force:
        return Outcome(target, Status.WARNED if target.is_symlink() else Status.SKIPPED, "existing entry differs; resolve ownership before replacing")
    temporary = target.with_name(f".{target.name}.{uuid4().hex}")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.symlink_to(desired_rel)
        temporary.replace(target)
        return Outcome(target, Status.REPLACED if exists else Status.CREATED, f"symlink -> {desired_rel}")
    except OSError as exc:
        return Outcome(target, Status.FAILED, f"could not install symlink: {exc}")
    finally:
        temporary.unlink(missing_ok=True)



def write_text_atomic(target: Path, content: str) -> None:
    """Install a complete UTF-8 file, preserving an existing file's mode."""
    if target.is_symlink():
        raise OSError(f"refusing to replace a symlink: {target}")
    mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o600
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, prefix=f".{target.name}.", delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
            os.fchmod(file.fileno(), mode)
        if target.is_symlink():
            raise OSError(f"destination became a symlink: {target}")
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def install_text(target: Path, content: str, existing: str | None) -> Outcome:
    """Replace an unchanged destination, returning a failed outcome on I/O errors."""
    try:
        actual = target.read_text() if target.exists() else None
        if actual != existing:
            return Outcome(target, Status.FAILED, "destination changed during sync; retry")
        write_text_atomic(target, content)
    except OSError as exc:
        return Outcome(target, Status.FAILED, f"could not install output: {exc}")
    status = Status.CREATED if existing is None else Status.REPLACED
    return Outcome(target, status, "new file" if existing is None else "overwrote diverging file", old_content=existing, new_content=content)


def sync_text(target: Path, content: str, force: bool = False, dry_run: bool = False) -> Outcome:
    """Write `content` to `target`, refusing to clobber a diverging file without force."""
    if target.is_symlink():
        return Outcome(target, Status.FAILED, "expected a regular file; destination is a symlink")
    if dry_run:
        if not target.exists():
            return Outcome(target, Status.WOULD_CREATE, "new file", new_content=content)
        existing = target.read_text()
        if existing == content:
            return Outcome(target, Status.UNCHANGED, "identical")
        return Outcome(target, Status.WOULD_REPLACE, "differs from source", old_content=existing, new_content=content)

    if not target.exists():
        return install_text(target, content, None)

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

    return install_text(target, content, existing)


def sync_json(target: Path, content: str, force: bool = False, dry_run: bool = False) -> Outcome:
    """Write JSON `content` to `target`, using semantic dict comparison to avoid false-positive drift."""
    if target.is_symlink():
        return Outcome(target, Status.FAILED, "expected a regular file; destination is a symlink")
    try:
        new_obj = json.loads(content)
    except json.JSONDecodeError as err:
        return Outcome(target, Status.FAILED, f"invalid JSON in source content: {err}")

    if not target.exists():
        if dry_run:
            return Outcome(target, Status.WOULD_CREATE, "new file", new_content=content)
        return install_text(target, content, None)

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

    return install_text(target, content, existing_text)


def sync_yaml(target: Path, content: str, force: bool = False, dry_run: bool = False) -> Outcome:
    """Write YAML `content` to `target`, using semantic dict comparison to avoid false-positive drift.

    Same contract as sync_json with YAML parsing: both sides are parsed and
    compared as objects, so key-order-only differences are UNCHANGED while
    any real value difference (including an unparseable existing target,
    which counts as diverging) needs `force` to overwrite.
    """
    if target.is_symlink():
        return Outcome(target, Status.FAILED, "expected a regular file; destination is a symlink")
    try:
        new_obj = yaml.safe_load(content)
    except yaml.YAMLError as err:
        return Outcome(target, Status.FAILED, f"invalid YAML in source content: {err}")

    if not target.exists():
        if dry_run:
            return Outcome(target, Status.WOULD_CREATE, "new file", new_content=content)
        return install_text(target, content, None)

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

    return install_text(target, content, existing_text)


def sync_dir_symlinks(
    target_dir: Path,
    source_dir: Path,
    force: bool = False,
    dry_run: bool = False,
) -> list[Outcome]:
    """Symlink each directory in source_dir into target_dir and handle orphans."""
    from settings_sync.ownership import prune_generated, sync_generated_symlink

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
        outcomes.append(sync_generated_symlink(target_sub, source_sub, force=force, dry_run=dry_run))

    outcomes.extend(prune_generated(target_dir, source_names, dry_run))
    return outcomes


def sync_dir_files(
    target_dir: Path,
    source_dir: Path,
    pattern: str = "*",
    force: bool = False,
    dry_run: bool = False,
    transform: Callable[[Path], tuple[str, list[str]]] | None = None,
    sync_fn: Callable[[Path, str, bool, bool], Outcome] | None = None,
) -> list[Outcome]:
    """Sync files matching pattern from source_dir to target_dir with orphan cleanup."""
    from settings_sync.ownership import prune_generated, sync_generated_file

    sync_fn = sync_fn or sync_generated_file
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

    outcomes.extend(prune_generated(target_dir, source_names, dry_run))
    return outcomes
