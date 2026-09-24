"""Track generated outputs so updates and cleanup preserve unrelated files."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Literal
from uuid import uuid4

from settings_sync.paths import state_home
from settings_sync.sync import Outcome, Status, install_text, sync_symlink, write_text_atomic


@dataclass(frozen=True, slots=True)
class ManagedEntry:
    source_id: str
    destination: Path
    kind: Literal["file", "symlink"]
    fingerprint: str


def fingerprint(path: Path) -> str:
    if path.is_symlink():
        return str(path.readlink())
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OwnershipStore:
    def __init__(self, path: Path | None = None):
        self.path = path if path is not None else state_home() / "managed.json"
        self.entries: dict[Path, ManagedEntry] = {}
        self.load()

    def load(self) -> None:
        self.entries = {}
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text())
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("entries"), list):
            raise ValueError("invalid ownership data; restore managed.json from backup before syncing")
        for item in data["entries"]:
            if not isinstance(item, dict) or not all(isinstance(item.get(key), str) for key in ("source_id", "destination", "kind", "fingerprint")):
                raise ValueError("invalid ownership entry; restore managed.json from backup before syncing")
            kind = item["kind"]
            if kind not in ("file", "symlink"):
                raise ValueError(f"invalid ownership kind: {kind}")
            destination = Path(item["destination"])
            if not destination.is_absolute() or ".." in destination.parts or destination in self.entries:
                raise ValueError(f"invalid or duplicate ownership destination: {destination}")
            self.entries[destination] = ManagedEntry(item["source_id"], destination, kind, item["fingerprint"])

    @contextmanager
    def lock(self, dry_run: bool) -> Iterator[None]:
        if dry_run:
            self.load()
            yield
            return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.path.parent / "sync.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.load()
            yield

    def get(self, destination: Path) -> ManagedEntry | None:
        return self.entries.get(Path(os.path.abspath(destination)))

    def save(self) -> None:
        data = [{**asdict(entry), "destination": str(entry.destination)} for entry in self.entries.values()]
        write_text_atomic(self.path, json.dumps({"version": 1, "entries": data}, indent=2) + "\n")

    def record(self, entry: ManagedEntry) -> None:
        if self.entries.get(entry.destination) == entry:
            return
        self.entries[entry.destination] = entry
        self.save()

    def forget(self, destination: Path) -> None:
        if self.entries.pop(Path(os.path.abspath(destination)), None) is not None:
            self.save()

    def backup(self, target: Path) -> Path:
        directory = self.path.parent / "backups"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = directory / f"{uuid4().hex}-{target.name}"
        shutil.copy2(target, backup, follow_symlinks=False)
        write_text_atomic(backup.with_name(backup.name + ".json"), json.dumps({"destination": str(Path(os.path.abspath(target))), "backup": str(backup)}) + "\n")
        return backup


def sync_generated_text(target: Path, source_id: str, content: str, store: OwnershipStore | None = None, force: bool = False, dry_run: bool = False) -> Outcome:
    """Update adopted output; preserve local edits unless explicitly backed up."""
    try:
        store = store if store is not None else OwnershipStore()
        with store.lock(dry_run):
            if target.is_symlink() or target.is_dir():
                return Outcome(target, Status.FAILED, "expected a generated regular file; preserve this entry and resolve its ownership")
            existing = target.read_text() if target.exists() else None
            entry = store.get(target)
            managed = entry is not None and entry.source_id == source_id and entry.kind == "file" and existing is not None and fingerprint(target) == entry.fingerprint
            conflict = existing is not None and existing != content and not managed
            if conflict and not force:
                return Outcome(target, Status.SKIPPED, "unmanaged or locally edited output; use --force on this step to back up and replace", existing, content)
            if existing == content:
                outcome = Outcome(target, Status.UNCHANGED, "identical")
            elif dry_run:
                return Outcome(target, Status.WOULD_CREATE if existing is None else Status.WOULD_REPLACE, "generated output differs", existing, content)
            else:
                backup = store.backup(target) if conflict else None
                outcome = install_text(target, content, existing)
                if backup is not None:
                    outcome.detail += f"; original backed up to {backup}"
            if not dry_run and outcome.status in (Status.CREATED, Status.REPLACED, Status.UNCHANGED):
                store.record(ManagedEntry(source_id, Path(os.path.abspath(target)), "file", fingerprint(target)))
            return outcome
    except (OSError, ValueError) as exc:
        return Outcome(target, Status.FAILED, f"could not sync generated output: {exc}")


def sync_generated_file(target: Path, content: str, force: bool = False, dry_run: bool = False) -> Outcome:
    return sync_generated_text(target, f"{target.parent.name}/{target.name}", content, force=force, dry_run=dry_run)


def sync_generated_json(target: Path, content: str, force: bool = False, dry_run: bool = False) -> Outcome:
    try:
        json.loads(content)
    except ValueError as exc:
        return Outcome(target, Status.FAILED, f"invalid generated JSON: {exc}")
    return sync_generated_file(target, content, force, dry_run)


def sync_generated_symlink(target: Path, source: Path, force: bool = False, dry_run: bool = False) -> Outcome:
    try:
        store = OwnershipStore()
        with store.lock(dry_run):
            if target.is_dir() and not target.is_symlink():
                return Outcome(target, Status.SKIPPED, "real directory preserved; inventory its contents before migrating")
            entry = store.get(target)
            exists = target.exists() or target.is_symlink()
            matching = target.is_symlink() and target.resolve() == source.resolve()
            managed = entry is not None and entry.kind == "symlink" and target.is_symlink() and fingerprint(target) == entry.fingerprint
            if exists and not matching and not managed and not force:
                return Outcome(target, Status.SKIPPED, "foreign link/file preserved; resolve ownership before replacing")
            backup = store.backup(target) if exists and not matching and not managed and force and not dry_run else None
            outcome = sync_symlink(target, source, force=managed or force, dry_run=dry_run)
            if backup is not None:
                outcome.detail += f"; original backed up to {backup}"
            if not dry_run and outcome.status in (Status.CREATED, Status.REPLACED, Status.UNCHANGED):
                store.record(ManagedEntry(f"{target.parent.name}/{target.name}", Path(os.path.abspath(target)), "symlink", fingerprint(target)))
            return outcome
    except (OSError, ValueError) as exc:
        return Outcome(target, Status.FAILED, f"could not sync generated link: {exc}")


def prune_generated(target_dir: Path, expected_names: set[str], dry_run: bool = False) -> list[Outcome]:
    """Remove only unchanged owned entries no longer produced by their source."""
    outcomes: list[Outcome] = []
    try:
        store = OwnershipStore()
        with store.lock(dry_run):
            for target, entry in list(store.entries.items()):
                if target.parent != Path(os.path.abspath(target_dir)) or target.name in expected_names:
                    continue
                if not target.exists() and not target.is_symlink():
                    if not dry_run:
                        store.forget(target)
                    continue
                kind = "symlink" if target.is_symlink() else "file"
                if target.is_dir() and not target.is_symlink() or kind != entry.kind or fingerprint(target) != entry.fingerprint:
                    outcomes.append(Outcome(target, Status.WARNED, "obsolete managed output has local changes; preserved"))
                    continue
                if dry_run:
                    outcomes.append(Outcome(target, Status.WOULD_REPLACE, "would remove unchanged managed output"))
                    continue
                target.unlink()
                store.forget(target)
                outcomes.append(Outcome(target, Status.REPLACED, "removed unchanged managed output"))
    except (OSError, ValueError) as exc:
        outcomes.append(Outcome(target_dir, Status.FAILED, f"could not clean generated outputs: {exc}"))
    return outcomes
