"""Outcome and Status behavior; action dataclasses are added in slice 3."""

from pathlib import Path

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
