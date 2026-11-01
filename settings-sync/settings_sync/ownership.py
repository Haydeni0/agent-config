"""One ownership record for files, symlinks, merged configs, and hook groups."""

import fcntl
import hashlib
import json
import os
import shutil
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from settings_sync.actions import Mode, Outcome, Status
from settings_sync.merging import canonicalize
from settings_sync.paths import state_home
from settings_sync.fsutil import write_text_atomic

HookGroups = dict[str, list[dict[str, object]]]
_RESTORE = "restore managed.json or the named snapshot from the backups directory before syncing"


@dataclass(frozen=True, slots=True)
class ManagedEntry:
    source_id: str
    destination: Path
    fingerprint: str


@dataclass(frozen=True, slots=True)
class KeyRecord:
    path: tuple[str, ...]
    value: object


@dataclass(frozen=True, slots=True)
class ConfigRecord:
    destination: Path
    codec: str
    keys: tuple[KeyRecord, ...] = ()
    hooks: HookGroups | None = None


def fingerprint(path: Path) -> str:
    if path.is_symlink():
        return str(path.readlink())
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OwnershipStore:
    def __init__(self, path: Path | None = None):
        self.path = path if path is not None else state_home() / "managed.json"
        self.files: dict[Path, ManagedEntry] = {}
        self.symlinks: dict[Path, ManagedEntry] = {}
        self.configs: dict[Path, ConfigRecord] = {}
        self._loaded = False

    # -- loading and migration --

    def load(self, mode: Mode) -> None:
        self.files, self.symlinks, self.configs = {}, {}, {}
        migrated = False
        if self.path.exists():
            text = self.path.read_text()
            try:
                data = json.loads(text)
            except ValueError as exc:
                raise ValueError(f"unparseable managed.json: {exc}; {_RESTORE}") from exc
            if not isinstance(data, dict):
                raise ValueError(f"invalid ownership data; {_RESTORE}")
            version = data.get("version")
            if version == 1:
                self._load_v1(data)
                migrated = True
            elif version == 2:
                self._load_v2(data)
            else:
                raise ValueError(f"unknown ownership version {version!r}; {_RESTORE}")
        folded_snapshots = self._fold_snapshots()
        if folded_snapshots:
            migrated = True
        self._loaded = True
        if migrated and mode is not Mode.DRY_RUN:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.path.exists():
                self.backup(self.path)
            self.save()
            for snapshot in folded_snapshots:
                snapshot.unlink()

    def _load_v1(self, data: dict) -> None:
        entries = data.get("entries")
        if not isinstance(entries, list):
            raise ValueError(f"invalid ownership data; {_RESTORE}")
        for item in entries:
            if not isinstance(item, dict) or not all(isinstance(item.get(key), str) for key in ("source_id", "destination", "kind", "fingerprint")):
                raise ValueError(f"invalid ownership entry; {_RESTORE}")
            self._add_entry(ManagedEntry(item["source_id"], Path(item["destination"]), item["fingerprint"]), item["kind"])

    def _load_v2(self, data: dict) -> None:
        for key in ("files", "symlinks"):
            if not isinstance(data.get(key), list):
                raise ValueError(f"invalid ownership data; {_RESTORE}")
        for item in data["files"]:
            self._add_entry(self._entry_from(item), "file")
        for item in data["symlinks"]:
            self._add_entry(self._entry_from(item), "symlink")
        configs = data.get("configs", [])
        if not isinstance(configs, list):
            raise ValueError(f"invalid ownership data; {_RESTORE}")
        for item in configs:
            record = self._config_from(item)
            self.configs[record.destination] = record

    def _entry_from(self, item: dict) -> ManagedEntry:
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) for key in ("source_id", "destination", "fingerprint")):
            raise ValueError(f"invalid ownership entry; {_RESTORE}")
        return ManagedEntry(item["source_id"], Path(item["destination"]), item["fingerprint"])

    def _config_from(self, item: dict) -> ConfigRecord:
        if not isinstance(item, dict) or not isinstance(item.get("destination"), str) or not isinstance(item.get("codec"), str):
            raise ValueError(f"invalid ownership config record; {_RESTORE}")
        raw_keys = item.get("keys", [])
        if not isinstance(raw_keys, list):
            raise ValueError(f"invalid ownership config record; {_RESTORE}")
        keys = []
        for record in raw_keys:
            if not isinstance(record, dict) or not isinstance(record.get("path"), list) or not all(isinstance(part, str) for part in record["path"]):
                raise ValueError(f"invalid ownership key record; {_RESTORE}")
            keys.append(KeyRecord(tuple(record["path"]), canonicalize(record.get("value"))))
        hooks = item.get("hooks")
        if hooks is not None and not isinstance(hooks, dict):
            raise ValueError(f"invalid ownership hook record; {_RESTORE}")
        return ConfigRecord(Path(item["destination"]), item["codec"], tuple(keys), hooks)

    def _add_entry(self, entry: ManagedEntry, kind: str) -> None:
        destination = Path(os.path.abspath(entry.destination))
        if not destination.is_absolute() or ".." in destination.parts:
            raise ValueError(f"invalid ownership destination: {destination}; {_RESTORE}")
        table = self.files if kind == "file" else self.symlinks
        if destination in table or destination in (self.files if kind == "symlink" else self.symlinks):
            raise ValueError(f"duplicate ownership destination: {destination}; {_RESTORE}")
        stored = ManagedEntry(entry.source_id, destination, entry.fingerprint)
        table[destination] = stored

    def _fold_snapshots(self) -> list[Path]:
        directory = self.path.parent / "hooks"
        if not directory.is_dir():
            return []
        folded: list[Path] = []
        for snapshot in sorted(directory.glob("*.json")):
            try:
                state = json.loads(snapshot.read_text())
            except ValueError as exc:
                raise ValueError(f"corrupt hook snapshot {snapshot}: {exc}; restore it from backups before syncing") from exc
            if (not isinstance(state, dict) or state.get("version") != 1
                    or not isinstance(state.get("target"), str) or not isinstance(state.get("hooks"), dict)):
                raise ValueError(f"invalid hook snapshot {snapshot}; {_RESTORE}")
            destination = Path(state["target"])
            if destination not in self.configs:
                self.configs[destination] = ConfigRecord(destination, "json", (), state["hooks"])
            folded.append(snapshot)
        return folded

    # -- persistence --

    def save(self) -> None:
        def entry_json(entry: ManagedEntry) -> dict:
            return {"source_id": entry.source_id, "destination": str(entry.destination), "fingerprint": entry.fingerprint}
        def config_json(record: ConfigRecord) -> dict:
            return {
                "destination": str(record.destination),
                "codec": record.codec,
                "keys": [{"path": list(key.path), "value": key.value} for key in record.keys],
                "hooks": record.hooks,
            }
        data = {
            "version": 2,
            "files": [entry_json(entry) for entry in sorted(self.files.values(), key=lambda e: str(e.destination))],
            "symlinks": [entry_json(entry) for entry in sorted(self.symlinks.values(), key=lambda e: str(e.destination))],
            "configs": [config_json(record) for record in sorted(self.configs.values(), key=lambda r: str(r.destination))],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_text_atomic(self.path, json.dumps(data, indent=2) + "\n")

    # -- records --

    def get(self, destination: Path) -> ManagedEntry | None:
        key = Path(os.path.abspath(destination))
        return self.files.get(key) or self.symlinks.get(key)

    def record_file(self, entry: ManagedEntry) -> None:
        key = Path(os.path.abspath(entry.destination))
        if self.files.get(key) == entry:
            return
        self.files[key] = entry
        self.save()

    def record_symlink(self, entry: ManagedEntry) -> None:
        key = Path(os.path.abspath(entry.destination))
        if self.symlinks.get(key) == entry:
            return
        self.symlinks[key] = entry
        self.save()

    def forget(self, destination: Path) -> None:
        key = Path(os.path.abspath(destination))
        if self.files.pop(key, None) is None and self.symlinks.pop(key, None) is None:
            return
        self.save()

    # -- merged-config records --

    def hooks_of(self, destination: Path) -> HookGroups:
        record = self.configs.get(Path(os.path.abspath(destination)))
        return dict(record.hooks) if record is not None and record.hooks is not None else {}

    def record_config(self, record: ConfigRecord) -> None:
        key = Path(os.path.abspath(record.destination))
        current = self.configs.get(key)
        if current is not None and current.keys == record.keys and current.hooks == record.hooks:
            return
        if current is not None and current.hooks != record.hooks and self.path.exists():
            self.backup(self.path)
        self.configs[key] = record
        self.save()

    # -- backups and locking --

    def backup(self, target: Path) -> Path:
        directory = self.path.parent / "backups"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = directory / f"{uuid4().hex}-{target.name}"
        shutil.copy2(target, backup, follow_symlinks=False)
        write_text_atomic(backup.with_name(backup.name + ".json"), json.dumps({"destination": str(Path(os.path.abspath(target))), "backup": str(backup)}) + "\n")
        return backup

    @contextmanager
    def lock(self, dry_run: bool) -> Iterator[None]:
        depth = getattr(_lock_state, "depth", 0)
        if depth == 0 and dry_run:
            self.load(Mode.DRY_RUN)
            yield
            return
        if not self._loaded and depth > 0:
            # An interim helper constructed its own store inside another lock:
            # it must still see current on-disk state.
            self.load(Mode.DRY_RUN if dry_run else Mode.APPLY)
        if depth == 0:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            handle = (self.path.parent / "sync.lock").open("a")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX)
                _lock_state.handle = handle
                self.load(Mode.APPLY)
            except BaseException:
                handle.close()  # a corrupt store must not leak the lock fd
                raise
        _lock_state.depth = depth + 1
        try:
            yield
        finally:
            _lock_state.depth = depth
            if depth == 0:
                fcntl.flock(_lock_state.handle, fcntl.LOCK_UN)
                _lock_state.handle.close()


_lock_state = threading.local()
