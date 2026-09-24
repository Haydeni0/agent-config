import json
import os
import pathlib

from settings_sync.sync import (
    Outcome,
    Status,
    sync_dir_files,
    sync_dir_symlinks,
    sync_json,
    sync_symlink,
    sync_text,
)


def test_outcome_properties_and_equality(tmp_path: pathlib.Path):
    p = tmp_path / "test.txt"
    o1 = Outcome(p, Status.CREATED, "created file")
    o2 = Outcome(p, Status.CREATED, "created file")
    o3 = Outcome(p, Status.UNCHANGED, "identical")

    assert o1.changed is True
    assert o3.changed is False
    assert o1 == o2
    assert o1 != o3
    assert repr(o1) == f"Outcome(path={p!r}, status={Status.CREATED!r}, detail='created file')"


def test_sync_symlink_create_and_idempotent(tmp_path: pathlib.Path):
    source = tmp_path / "source_dir"
    source.mkdir()
    target = tmp_path / "target_link"

    # 1. Create
    outcome = sync_symlink(target, source)
    assert outcome.status == Status.CREATED
    assert target.is_symlink()
    assert target.resolve() == source.resolve()

    # 2. Already correct
    outcome_repeat = sync_symlink(target, source)
    assert outcome_repeat.status == Status.UNCHANGED
    assert outcome_repeat.detail == "already correct"


def test_sync_symlink_retarget_with_force(tmp_path: pathlib.Path):
    source1 = tmp_path / "src1"
    source1.mkdir()
    source2 = tmp_path / "src2"
    source2.mkdir()
    target = tmp_path / "link"

    sync_symlink(target, source1)

    # Without force -> warn
    outcome = sync_symlink(target, source2, force=False)
    assert outcome.status == Status.WARNED
    assert target.resolve() == source1.resolve()

    # With force -> retarget
    outcome = sync_symlink(target, source2, force=True)
    assert outcome.status == Status.REPLACED
    assert target.resolve() == source2.resolve()


def test_sync_symlink_replaces_file_but_preserves_directory(tmp_path: pathlib.Path):
    source = tmp_path / "source"
    source.mkdir()

    # Real file target
    file_target = tmp_path / "real_file"
    file_target.write_text("real")
    outcome_file_noforce = sync_symlink(file_target, source, force=False)
    assert outcome_file_noforce.status == Status.SKIPPED
    assert not file_target.is_symlink()

    outcome_file_force = sync_symlink(file_target, source, force=True)
    assert outcome_file_force.status == Status.REPLACED
    assert file_target.is_symlink()

    # Real dir target
    dir_target = tmp_path / "real_dir"
    dir_target.mkdir()
    (dir_target / "nested.txt").write_text("nested")
    outcome_dir_force = sync_symlink(dir_target, source, force=True)
    assert outcome_dir_force.status == Status.SKIPPED
    assert (dir_target / "nested.txt").read_text() == "nested"


def test_sync_symlink_dry_run(tmp_path: pathlib.Path):
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "link"

    # Would create
    outcome = sync_symlink(target, source, dry_run=True)
    assert outcome.status == Status.WOULD_CREATE
    assert not target.exists()

    # Real create
    sync_symlink(target, source)

    # Would unchanged
    outcome = sync_symlink(target, source, dry_run=True)
    assert outcome.status == Status.UNCHANGED

    # Would replace
    source2 = tmp_path / "source2"
    source2.mkdir()
    outcome = sync_symlink(target, source2, dry_run=True)
    assert outcome.status == Status.WOULD_REPLACE


def test_sync_text_crud_and_dry_run(tmp_path: pathlib.Path):
    target = tmp_path / "file.txt"

    # 1. Dry run create
    outcome = sync_text(target, "hello\n", dry_run=True)
    assert outcome.status == Status.WOULD_CREATE
    assert not target.exists()

    # 2. Real create
    outcome = sync_text(target, "hello\n")
    assert outcome.status == Status.CREATED
    assert target.read_text() == "hello\n"

    # 3. Unchanged
    outcome = sync_text(target, "hello\n")
    assert outcome.status == Status.UNCHANGED

    # 4. Dry run replace
    outcome = sync_text(target, "world\n", dry_run=True)
    assert outcome.status == Status.WOULD_REPLACE
    assert target.read_text() == "hello\n"

    # 5. Skip without force
    outcome = sync_text(target, "world\n", force=False)
    assert outcome.status == Status.SKIPPED
    assert target.read_text() == "hello\n"

    # 6. Overwrite with force
    outcome = sync_text(target, "world\n", force=True)
    assert outcome.status == Status.REPLACED
    assert target.read_text() == "world\n"


def test_sync_json_creates_new_file(tmp_path: pathlib.Path):
    target = tmp_path / "settings.json"
    outcome = sync_json(target, '{"a": 1, "b": 2}\n')
    assert outcome.status == Status.CREATED
    assert target.is_file()
    assert json.loads(target.read_text()) == {"a": 1, "b": 2}


def test_sync_json_identical_semantic_content(tmp_path: pathlib.Path):
    target = tmp_path / "settings.json"
    target.write_text('{\n  "b": 2,\n  "a": 1\n}\n')
    # Same dict, different key order/formatting
    outcome = sync_json(target, '{"a": 1, "b": 2}\n')
    assert outcome.status == Status.UNCHANGED
    assert outcome.detail == "identical"


def test_sync_json_detects_semantic_diff(tmp_path: pathlib.Path):
    target = tmp_path / "settings.json"
    target.write_text('{"a": 1, "b": 3}\n')
    outcome = sync_json(target, '{"a": 1, "b": 2}\n', force=False)
    assert outcome.status == Status.SKIPPED
    assert "differs" in outcome.detail


def test_sync_json_dry_run(tmp_path: pathlib.Path):
    target = tmp_path / "settings.json"

    # Dry run create
    outcome = sync_json(target, '{"a": 1}\n', dry_run=True)
    assert outcome.status == Status.WOULD_CREATE
    assert not target.exists()

    # Create
    sync_json(target, '{"a": 1}\n')

    # Dry run identical
    outcome = sync_json(target, '{"a": 1}\n', dry_run=True)
    assert outcome.status == Status.UNCHANGED

    # Dry run replace
    outcome = sync_json(target, '{"a": 2}\n', dry_run=True)
    assert outcome.status == Status.WOULD_REPLACE


def test_sync_json_rejects_invalid_source_json(tmp_path: pathlib.Path):
    target = tmp_path / "settings.json"
    outcome = sync_json(target, '{"a": 1, broken json')
    assert outcome.status == Status.FAILED
    assert "invalid JSON" in outcome.detail
    assert not target.exists()


def test_sync_dir_symlinks_missing_source_dir(tmp_path: pathlib.Path):
    source_dir = tmp_path / "nonexistent"
    target_dir = tmp_path / "dst"
    target_dir.mkdir(parents=True)
    (target_dir / "existing-file").write_text("keep me")

    outcomes = sync_dir_symlinks(target_dir, source_dir, force=True)
    assert len(outcomes) == 1
    assert outcomes[0].status == Status.NO_SOURCE
    assert (target_dir / "existing-file").exists()


def test_sync_dir_symlinks_creates_and_cleans_orphans(tmp_path: pathlib.Path):
    source_dir = tmp_path / "src"
    (source_dir / "skill-a").mkdir(parents=True)
    (source_dir / "skill-b").mkdir(parents=True)

    target_dir = tmp_path / "dst"
    target_dir.mkdir(parents=True)
    (target_dir / "orphan-skill").mkdir(parents=True)

    sync_dir_symlinks(target_dir, source_dir)
    (source_dir / "skill-a").rmdir()
    outcomes = sync_dir_symlinks(target_dir, source_dir, force=True)
    assert (target_dir / "orphan-skill").is_dir()
    assert not (target_dir / "skill-a").is_symlink()
    assert (target_dir / "skill-b").is_symlink()
    assert any(o.path.name == "skill-a" and o.status == Status.REPLACED for o in outcomes)



def test_sync_dir_files_with_orphans(tmp_path: pathlib.Path):
    source_dir = tmp_path / "src"
    source_dir.mkdir(parents=True)
    (source_dir / "provider-a.json").write_text('{"name": "a"}')

    target_dir = tmp_path / "dst"
    target_dir.mkdir(parents=True)
    (target_dir / "orphan.json").write_text('{"name": "orphan"}')

    sync_dir_files(target_dir, source_dir, pattern="*.json")
    (source_dir / "provider-a.json").unlink()
    outcomes = sync_dir_files(target_dir, source_dir, pattern="*.json", force=True)
    assert (target_dir / "orphan.json").read_text() == '{"name": "orphan"}'
    assert not (target_dir / "provider-a.json").exists()
    assert any(o.path.name == "provider-a.json" and o.status == Status.REPLACED for o in outcomes)
