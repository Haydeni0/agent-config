"""Executor policy-table behavior, driven directly at seam B."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from settings_sync.actions import Directory, Effect, File, MergedConfig, Mode, Outcome, Probe, Prune, Regenerate, Report, Status, Symlink
from settings_sync.executor import execute
from settings_sync.merging import JsonCodec, YamlCodec
from settings_sync.ownership import OwnershipStore


def store_for(isolated_home: Path) -> OwnershipStore:
    return OwnershipStore(isolated_home / ".local" / "state" / "agent-config" / "managed.json")


def group(command: str) -> dict[str, object]:
    return {"matcher": "Bash", "hooks": [{"type": "command", "command": command}]}


# ---- File ----

def test_file_adopts_identical_unrecorded_output(isolated_home: Path):
    target = isolated_home / "f"
    target.write_text("body")
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    outcomes = execute([File(target, "body")], Mode.APPLY, store)
    assert outcomes[0].status == Status.UNCHANGED
    assert store.get(target) is not None


def test_file_conflict_skips_then_force_backs_up(isolated_home: Path):
    target = isolated_home / "f"
    target.write_text("local edit")
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    outcome = execute([File(target, "shared")], Mode.APPLY, store)[0]
    assert outcome.status == Status.SKIPPED
    assert target.read_text() == "local edit"
    outcome = execute([File(target, "shared")], Mode.FORCE, store)[0]
    assert outcome.status == Status.REPLACED
    assert target.read_text() == "shared"
    backups = isolated_home / ".local/state/agent-config/backups"
    assert any(p.read_text() == "local edit" for p in backups.rglob("*") if p.is_file())


def test_file_managed_source_update_needs_no_force(isolated_home: Path):
    target = isolated_home / "f"
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    execute([File(target, "one")], Mode.APPLY, store)
    outcome = execute([File(target, "two")], Mode.APPLY, store)[0]
    assert outcome.status == Status.REPLACED


def test_file_preview_writes_nothing(isolated_home: Path):
    target = isolated_home / "f"
    store = store_for(isolated_home)
    store.load(Mode.DRY_RUN)
    outcomes = execute([File(target, "x")], Mode.DRY_RUN, store)
    assert outcomes[0].status == Status.WOULD_CREATE
    assert not target.exists()


# ---- Symlink ----

def test_symlink_real_directory_fails_even_under_force(isolated_home: Path):
    target = isolated_home / "link"
    target.mkdir()
    (target / "keep").write_text("x")
    store = store_for(isolated_home)
    store.load(Mode.FORCE)
    outcome = execute([Symlink(target, isolated_home / "src")], Mode.FORCE, store)[0]
    assert outcome.status == Status.FAILED
    assert (target / "keep").exists()


def test_symlink_managed_stale_link_updates_without_force(isolated_home: Path):
    old = isolated_home / "old"; old.mkdir()
    new = isolated_home / "new"; new.mkdir()
    target = isolated_home / "link"
    target.symlink_to(old)
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    from settings_sync.ownership import ManagedEntry
    execute([Symlink(target, old)], Mode.APPLY, store)  # record it
    outcome = execute([Symlink(target, new)], Mode.APPLY, store)[0]
    assert outcome.status == Status.REPLACED
    assert target.resolve() == new.resolve()


def test_symlink_detail_forces_conflict_treatment(isolated_home: Path):
    old = isolated_home / "old"; old.mkdir()
    new = isolated_home / "new"; new.mkdir()
    target = isolated_home / "link"
    target.symlink_to(old)
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    from settings_sync.ownership import ManagedEntry
    execute([Symlink(target, old)], Mode.APPLY, store)  # managed
    outcome = execute([Symlink(target, new, detail="reconcile entries first")], Mode.APPLY, store)[0]
    assert outcome.status == Status.SKIPPED
    assert "reconcile entries first" in outcome.detail
    outcome = execute([Symlink(target, new, detail="reconcile entries first")], Mode.FORCE, store)[0]
    assert outcome.status == Status.REPLACED


# ---- MergedConfig (slice 3: merge, messages, legacy migration, hooks) ----

def test_merged_config_reports_changed_paths(isolated_home: Path):
    target = isolated_home / "settings.json"
    target.write_text(json.dumps({"model": "local", "keep": True}))
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    outcome = execute([MergedConfig(target, JsonCodec(), {"model": "shared"})], Mode.APPLY, store)[0]
    assert outcome.status == Status.MERGED
    assert "changed: model" in outcome.detail
    assert "replaced" not in outcome.status
    assert json.loads(target.read_text()) == {"model": "shared", "keep": True}


def test_merged_config_check_previews_would_merge(isolated_home: Path):
    target = isolated_home / "settings.json"
    target.write_text(json.dumps({"model": "local"}))
    store = store_for(isolated_home)
    store.load(Mode.DRY_RUN)
    outcome = execute([MergedConfig(target, JsonCodec(), {"model": "shared"})], Mode.DRY_RUN, store)[0]
    assert outcome.status == Status.WOULD_MERGE
    assert "changed: model" in outcome.detail
    assert json.loads(target.read_text()) == {"model": "local"}


def test_merged_config_semantic_equality_is_unchanged(isolated_home: Path):
    target = isolated_home / "settings.json"
    target.write_text('{\n  "b": 2,\n  "a": 1\n}\n')
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    outcome = execute([MergedConfig(target, JsonCodec(), {"a": 1, "b": 2})], Mode.APPLY, store)[0]
    assert outcome.status == Status.UNCHANGED
    assert target.read_text() == '{\n  "b": 2,\n  "a": 1\n}\n'


def test_merged_config_invalid_target_fails_under_force(isolated_home: Path):
    target = isolated_home / "settings.json"
    target.write_text("[broken")
    store = store_for(isolated_home)
    store.load(Mode.FORCE)
    outcome = execute([MergedConfig(target, JsonCodec(), {"a": 1})], Mode.FORCE, store)[0]
    assert outcome.status == Status.FAILED
    assert target.read_text() == "[broken"


def test_merged_config_legacy_conflict_skips_without_force(isolated_home: Path):
    target = isolated_home / "opencode.json"
    legacy = target.with_suffix(".jsonc")
    legacy.write_text(json.dumps({"model": "legacy", "localOnly": "keep"}))
    target.write_text(json.dumps({"model": "local"}))
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    action = MergedConfig(target, JsonCodec(), {"$schema": "s", "model": "shared"},
                          migrate={"model": "legacy", "localOnly": "keep"}, remove_after=legacy)
    outcome = execute([action], Mode.APPLY, store)[0]
    assert outcome.status == Status.SKIPPED
    assert json.loads(target.read_text()) == {"model": "local"}
    assert legacy.exists()


def test_merged_config_legacy_migration_template_wins_and_cleans_up(isolated_home: Path):
    target = isolated_home / "opencode.json"
    legacy = target.with_suffix(".jsonc")
    legacy.write_text(json.dumps({"model": "legacy", "localOnly": "keep"}))
    store = store_for(isolated_home)
    store.load(Mode.FORCE)
    action = MergedConfig(target, JsonCodec(), {"$schema": "s", "model": "shared"},
                          migrate={"model": "legacy", "localOnly": "keep"}, remove_after=legacy)
    outcome = execute([action], Mode.FORCE, store)[0]
    assert outcome.status == Status.MERGED
    written = json.loads(target.read_text())
    assert written["model"] == "shared"          # template wins shared keys
    assert written["localOnly"] == "keep"        # migrating key carried untracked
    assert not legacy.exists()
    migrated_keys = [k.path for rec in [store.configs.get(target)] if rec for k in rec.keys]
    assert migrated_keys == []                    # migrating keys never recorded


def test_merged_config_hooks_conflict_is_force_immune(isolated_home: Path):
    target = isolated_home / "settings.json"
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    desired = {"hooks": {"PreToolUse": [group("shared")]}}
    execute([MergedConfig(target, JsonCodec(), desired, hook_key="hooks")], Mode.APPLY, store)
    config = json.loads(target.read_text())
    config["hooks"]["PreToolUse"][0]["matcher"] = "Read"
    target.write_text(json.dumps(config))
    before = target.read_bytes()
    outcome = execute([MergedConfig(target, JsonCodec(), desired, hook_key="hooks")], Mode.FORCE, store)[0]
    assert outcome.status == Status.FAILED
    assert target.read_bytes() == before


def test_merged_config_hook_backups_before_change(isolated_home: Path):
    target = isolated_home / "settings.json"
    target.write_text(json.dumps({"local": True}))
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    execute([MergedConfig(target, JsonCodec(), {"hooks": {"PreToolUse": [group("shared")]}}, hook_key="hooks")], Mode.APPLY, store)
    backups = isolated_home / ".local/state/agent-config/backups"
    assert any(p.is_file() and p.read_text() == json.dumps({"local": True}) for p in backups.rglob("*"))


# ---- Regenerate ----

def test_regenerate_ignores_local_edits_and_detects_semantic_equality(isolated_home: Path):
    target = isolated_home / "config.yaml"
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    execute([Regenerate(target, "a: 1\n")], Mode.APPLY, store)
    target.write_text("hand: edit\n")
    outcome = execute([Regenerate(target, "a: 1\n")], Mode.APPLY, store)[0]
    assert outcome.status == Status.REPLACED
    assert target.read_text() == "a: 1\n"
    target.write_text("b: 2\na: 1\n")
    outcome = execute([Regenerate(target, "a: 1\nb: 2\n")], Mode.APPLY, store)[0]
    assert outcome.status == Status.UNCHANGED


# ---- Prune ----

def test_prune_removes_only_unchanged_recorded_entries(isolated_home: Path):
    directory = isolated_home / "out"
    directory.mkdir()
    keep = directory / "keep"; keep.write_text("keep")
    stale = directory / "stale"; stale.write_text("stale")
    edited = directory / "edited"; edited.write_text("old")  # original managed content
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    from settings_sync.ownership import ManagedEntry
    import hashlib
    for name, content in (("keep", "keep"), ("stale", "stale"), ("edited", "old")):
        path = directory / name
        store.record_file(ManagedEntry(f"out/{name}", path, hashlib.sha256(content.encode()).hexdigest()))
    edited.write_text("local")  # local edit after recording: fingerprint now mismatches
    outcomes = execute([Prune(directory, frozenset({"keep"}))], Mode.APPLY, store)
    by_name = {o.path.name: o.status for o in outcomes}
    assert by_name == {"stale": Status.REPLACED, "edited": Status.WARNED}
    assert keep.read_text() == "keep"
    assert not stale.exists()
    assert edited.read_text() == "local"
    assert store.get(stale) is None


# ---- Effect / Probe / Report ----

def test_effect_runs_only_when_pending(isolated_home: Path):
    ran: list[str] = []

    def fresh(pending: bool) -> Effect:
        return Effect(isolated_home / "side", pending, "do it", lambda: ran.append("x"))

    store = store_for(isolated_home)
    store.load(Mode.DRY_RUN)
    assert execute([fresh(True)], Mode.DRY_RUN, store)[0].status == Status.WOULD_CREATE
    store.load(Mode.APPLY)
    assert execute([fresh(True)], Mode.APPLY, store)[0].status == Status.CREATED
    # a fresh plan sees the side effect already applied: pending False, so UNCHANGED
    assert execute([fresh(False)], Mode.APPLY, store)[0].status == Status.UNCHANGED
    assert ran == ["x"]


def test_effect_failure_is_one_failed_outcome(isolated_home: Path):
    def boom() -> None:
        raise RuntimeError("telemetry exit 1")
    from settings_sync.actions import Effect
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    outcome = execute([Effect(isolated_home / "t", True, "telemetry off", boom)], Mode.APPLY, store)[0]
    assert outcome.status == Status.FAILED
    assert "telemetry" in outcome.detail


def test_probe_runs_only_in_dry_run(isolated_home: Path):
    from settings_sync.actions import Probe
    ran: list[int] = []
    def check() -> Outcome:
        ran.append(1)
        return Outcome(isolated_home / "p", Status.WARNED, "off PATH")
    store = store_for(isolated_home)
    store.load(Mode.DRY_RUN)
    assert execute([Probe(isolated_home / "p", check)], Mode.DRY_RUN, store)[0].status == Status.WARNED
    store.load(Mode.APPLY)
    assert execute([Probe(isolated_home / "p", check)], Mode.APPLY, store) == []
    assert len(ran) == 1


def test_report_passes_through(isolated_home: Path):
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    outcome = execute([Report(isolated_home / "s", Status.WARNED, "lint finding")], Mode.FORCE, store)[0]
    assert (outcome.status, outcome.detail) == (Status.WARNED, "lint finding")


# ---- Directory ----

def test_directory_creates_and_repairs_mode(isolated_home: Path):
    directory = isolated_home / "runtime"
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    assert execute([Directory(directory, 0o700)], Mode.APPLY, store)[0].status == Status.CREATED
    directory.chmod(0o755)
    assert execute([Directory(directory, 0o700)], Mode.APPLY, store)[0].status == Status.REPLACED
    assert directory.stat().st_mode & 0o777 == 0o700
    directory.rmdir(); directory.write_text("not a dir")
    assert execute([Directory(directory, 0o700)], Mode.APPLY, store)[0].status == Status.FAILED


# ---- Invariants (S60-S63) ----

def test_replace_failure_preserves_original(isolated_home: Path, mocker: MockerFixture):
    target = isolated_home / "f"
    target.write_text("before")
    target.chmod(0o640)
    mocker.patch("pathlib.Path.replace", side_effect=OSError("disk unavailable"))
    store = store_for(isolated_home)
    store.load(Mode.FORCE)
    outcome = execute([File(target, "after")], Mode.FORCE, store)[0]
    assert outcome.status == Status.FAILED
    assert target.read_text() == "before"
    assert target.stat().st_mode & 0o777 == 0o640
    assert not list(target.parent.glob(f".{target.name}.*")), "temp file left behind"


def test_regular_output_rejects_symlink(isolated_home: Path):
    source = isolated_home / "s"; source.write_text("keep")
    target = isolated_home / "t"; target.symlink_to(source)
    store = store_for(isolated_home)
    store.load(Mode.FORCE)
    for action in (File(target, "x"), MergedConfig(target, JsonCodec(), {"a": 1}), Regenerate(target, "a: 1\n")):
        outcome = execute([action], Mode.FORCE, store)[0]
        assert outcome.status == Status.FAILED
    assert source.read_text() == "keep"


def test_native_edit_during_merge_preserved(isolated_home: Path, mocker: MockerFixture):
    target = isolated_home / "settings.json"
    target.write_text('{"original": true}')
    original_read = Path.read_text

    def read_then_native_edit(path: Path, *args: object, **kwargs: object) -> str:
        content = original_read(path)
        if path == target:
            target.write_text('{"native": "changed"}')
        return content

    mocker.patch.object(Path, "read_text", read_then_native_edit)
    store = store_for(isolated_home)
    store.load(Mode.APPLY)
    outcome = execute([MergedConfig(target, JsonCodec(), {"managed": True})], Mode.APPLY, store)[0]
    assert outcome.status == Status.FAILED
    assert target.read_bytes() == b'{"native": "changed"}'


def test_concurrent_merges_yield_exactly_one_changed(isolated_home: Path):
    target = isolated_home / "settings.json"
    target.write_text(json.dumps({"hooks": {"PreToolUse": [group("local")]}}))
    desired = {"hooks": {"PreToolUse": [group("shared")]}}
    action = MergedConfig(target, JsonCodec(), desired, hook_key="hooks")

    def run_once(_: int) -> list[Outcome]:
        store = store_for(isolated_home)
        store.load(Mode.APPLY)
        return execute([action], Mode.APPLY, store)

    with ThreadPoolExecutor(max_workers=4) as executor:
        outcomes = [o for result in executor.map(run_once, range(4)) for o in result]
    assert [o.status for o in outcomes].count(Status.MERGED) + [o.status for o in outcomes].count(Status.REPLACED) == 1
    assert all(o.status in (Status.MERGED, Status.REPLACED, Status.UNCHANGED) for o in outcomes)
    assert json.loads(target.read_text())["hooks"]["PreToolUse"] == [group("local"), group("shared")]
