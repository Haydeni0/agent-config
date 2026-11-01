"""Outcome and Status behavior; action dataclasses are added in slice 3."""

from pathlib import Path

import pytest

from settings_sync.actions import Outcome, Status


def test_outcome_is_a_field_equality_dataclass(tmp_path: Path) -> None:
    path = tmp_path / "f"
    same = Outcome(path, Status.CREATED, "new file")
    assert same == Outcome(path, Status.CREATED, "new file")
    assert same != Outcome(path, Status.CREATED, "new file", old_content="x")
    assert same != Outcome(path, Status.UNCHANGED, "new file")


def test_status_is_a_str_enum() -> None:
    assert Status.SKIPPED == "skipped"
    assert not hasattr(Status, "WOULD_SKIP")
    assert {Status.WARNED, Status.FAILED} == {"warned", "failed"}


def test_actions_are_frozen_value_objects(tmp_path: Path) -> None:
    from settings_sync.actions import File, MergedConfig, Prune, Report, Symlink
    from settings_sync.merging import JsonCodec

    file = File(tmp_path / "f", "body")
    with pytest.raises(Exception):
        file.content = "x"
    merged = MergedConfig(tmp_path / "c", JsonCodec(), {"model": "shared"}, hook_key="hooks")
    assert merged.hook_key == "hooks"
    assert merged.migrate is None and merged.remove_after is None
    link = Symlink(tmp_path / "l", tmp_path, detail="resolve before replacing")
    assert link.detail
    assert Report(tmp_path, Status.WARNED, "finding").status == Status.WARNED
    assert Prune(tmp_path, frozenset({"a"})).expected == frozenset({"a"})


def test_status_knows_merged_and_would_merge() -> None:
    assert Status.MERGED == "merged"
    assert Status.WOULD_MERGE == "would_merge"
