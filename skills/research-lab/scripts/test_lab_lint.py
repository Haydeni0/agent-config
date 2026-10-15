"""Tests for lab_lint.py: future stamps, status.md shape, audit vocabulary.

Timestamp tests pin the file mtime with ``os.utime`` so they do not depend on
when they run; HH:MM-with-date-context cases write today's date into the file.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import lab_lint as ll  # noqa: E402

NOW = time.time()
HOUR = 3600


def _pin_mtime(path: Path, when: float) -> None:
    os.utime(path, (when, when))


def _iso(when: float) -> str:
    return datetime.fromtimestamp(when).strftime("%Y-%m-%d %H:%M")


def _make_lab(tmp_path: Path) -> Path:
    (tmp_path / "audit").mkdir()
    (tmp_path / "status.md").write_text(
        "E1 running: 2/3 experiments decided, page draft up.\n\n"
        "| by | milestone | state |\n|---|---|---|\n| 18:00 | page audited | [x] |\n\n"
        "| id | question | tier | state | budget | eta |\n"
        "|---|---|---|---|---|---|\n"
        "| E1 | does B dominate? | headline | [x] | 2 h | eta 18:00 |\n"
    )
    (tmp_path / "audit" / "log.md").write_text(
        "# Audit log\n\n"
        "Events: `GATE` `CATCH` (see template).\n\n"
        "| Time | Event | Experiment | Outcome | Detail | Evidence |\n"
        "|---|---|---|---|---|---|\n"
        f"| {_iso(NOW - HOUR)} | CATCH | E1 | fixed | rounding drift | audit/E1.md |\n"
        f"| {_iso(NOW - HOUR)} | GATE | E1 | PASS | result audit | audit/E1.md |\n"
    )
    return tmp_path


def _run(lab: Path, monkeypatch, capsys) -> tuple[int, str]:
    monkeypatch.setattr(sys, "argv", ["lab_lint.py", str(lab)])
    rc = ll.main()
    return rc, capsys.readouterr().out


def test_clean_lab_passes(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    for p in lab.rglob("*"):
        if p.is_file():
            _pin_mtime(p, NOW)
    rc, out = _run(lab, monkeypatch, capsys)
    assert rc == 0, out
    assert "lab lint: clean" in out


def test_future_iso_stamp_fails(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    entry = lab / "experiments"
    entry.mkdir()
    f = entry / "E1.md"
    f.write_text(f"## Entry\n\nClosed {_iso(NOW + HOUR)} after the run.\n")
    _pin_mtime(f, NOW)
    rc, out = _run(lab, monkeypatch, capsys)
    assert rc == 1
    assert "future-stamp" in out
    assert "E1.md:3" in out  # reported with file and line
    assert _iso(NOW + HOUR) in out  # and the stamp


def test_future_iso_in_jsonl_fails(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    f = lab / "mail.jsonl"
    f.write_text('{"ts": "%s", "ring": true}\n' % datetime.fromtimestamp(NOW + HOUR).isoformat())
    _pin_mtime(f, NOW)
    rc, out = _run(lab, monkeypatch, capsys)
    assert rc == 1
    assert "mail.jsonl:1" in out and "future-stamp" in out


def test_bare_hhmm_with_today_date_context_fails(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    today = datetime.fromtimestamp(NOW).date().isoformat()
    later = (datetime.fromtimestamp(NOW) + timedelta(hours=1)).strftime("%H:%M")
    f = lab / "friction.md"
    f.write_text(f"## Friction ({today})\n\nBlocker reached the overseer at {later}.\n")
    _pin_mtime(f, NOW)
    rc, out = _run(lab, monkeypatch, capsys)
    assert rc == 1
    assert "friction.md:3" in out and later in out


def test_bare_hhmm_without_date_context_not_checked(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    later = (datetime.fromtimestamp(NOW) + timedelta(hours=1)).strftime("%H:%M")
    f = lab / "friction.md"
    f.write_text(f"Blocker reached the overseer at {later}.\n")  # no date anywhere
    _pin_mtime(f, NOW)
    rc, out = _run(lab, monkeypatch, capsys)
    assert rc == 0, out


def test_past_stamps_clean(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    f = lab / "notes.md"
    f.write_text(f"{today_str()}\nStarted {_iso(NOW - 2 * HOUR)}, closed at 09:15.\n")
    _pin_mtime(f, NOW - HOUR)
    rc, out = _run(lab, monkeypatch, capsys)
    assert rc == 0, out


def test_planned_times_are_exempt(tmp_path, monkeypatch, capsys):
    # deadline/due/by/until/eta/cap/target/window/gate/before/next + "at the latest"
    # mark a time as planned; a by/eta table column does too (pilot labs carry
    # "hard deadline 18:30", "done by 16:50", "run window 17:15-17:20", ...)
    lab = _make_lab(tmp_path)
    later = (datetime.fromtimestamp(NOW) + timedelta(hours=1)).strftime("%H:%M")
    f = lab / "plan.md"
    f.write_text(
        f"{today_str()}\n"
        f"Hard deadline {later}.\n"
        f"Numbers due {later}.\n"
        f"Done to PI by {later}.\n"
        f"Cut if not complete until {later}.\n"
        f"eta {later}.\n"
        f"Hard cap {later}.\n"
        f"Target {later}.\n"
        f"Run window {later}.\n"
        f"Gate {later}.\n"
        f"Before {later}.\n"
        f"Next sync {later}.\n"
        f"Report at the latest {later}.\n"
        f"Deadline to {later}.\n"
        f"verdicts by ~{later}.\n"
        f"| by | milestone | state |\n|---|---|---|\n| {later} | page audited | [x] |\n\n"
        f"| id | question | tier | state | budget | eta |\n"
        f"|---|---|---|---|---|---|\n| E1 | q? | headline | [x] | 2 h | {later} |\n"
    )
    _pin_mtime(f, NOW)
    rc, out = _run(lab, monkeypatch, capsys)
    assert rc == 0, out


def test_planned_exemptions_do_not_swallow_real_projections(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    later = (datetime.fromtimestamp(NOW) + timedelta(hours=1)).strftime("%H:%M")
    f = lab / "events.md"
    f.write_text(
        f"{today_str()}\n"
        # agentive "by" (launched by author-2) must not exempt the launch stamp
        f"Launched by author-2 at ~{later} via local-claude.\n"
        # a decision entry stamped ahead of its write time
        f"- D7 ({today_str()}, {later}). Decision on E1: ACCEPTED.\n"
        # a plain projected event time
        f"Closed at {later}.\n"
        # "by" two words back with a noun between is still agentive-shaped: exempt
        # only when adjacent, so this stays a hit
        f"Checked and logged by author-2 at {later}.\n"
    )
    _pin_mtime(f, NOW)
    rc, out = _run(lab, monkeypatch, capsys)
    assert rc == 1
    assert out.count("future-stamp") == 4
    assert later in out
    assert "events.md:2" in out  # agentive "launched by author-2 at ~HH:MM" still caught


def today_str() -> str:
    return datetime.fromtimestamp(NOW).date().isoformat()


def test_status_line1_not_a_state_fails(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    (lab / "status.md").write_text(
        "# Lab status\n\n"
        "| by | milestone | state |\n|---|---|---|\n"
        "| id | question | tier | state | budget | eta |\n|---|---|---|---|---|---|\n"
    )
    rc, out = _run(lab, monkeypatch, capsys)
    assert rc == 1
    assert "line 1 is not a one-line state" in out


@pytest.mark.parametrize(
    "drop, table",
    [(("| by | milestone | state |",), "milestone"), ((" | id | question | tier | state | budget | eta |",), "experiment")],
)
def test_missing_status_table_fails(tmp_path, monkeypatch, capsys, drop, table):
    lab = _make_lab(tmp_path)
    lines = (lab / "status.md").read_text().splitlines()
    kept = [l for l in lines if l.strip() not in {d.strip() for d in drop}]
    (lab / "status.md").write_text("\n".join(kept) + "\n")
    rc, out = _run(lab, monkeypatch, capsys)
    assert rc == 1
    assert f"{table} table missing" in out


def test_status_or_audit_missing_fails(tmp_path, monkeypatch, capsys):
    (tmp_path / "audit").mkdir()
    rc, out = _run(tmp_path, monkeypatch, capsys)
    assert rc == 1
    assert "status.md missing" in out and "audit/log.md missing" in out


def test_audit_event_outside_vocabulary_fails(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    log = lab / "audit" / "log.md"
    log.write_text(
        "| Time | Event | Experiment | Outcome | Detail | Evidence |\n"
        "|---|---|---|---|---|---|\n"
        f"| {_iso(NOW - HOUR)} | PROGRESS | E1 | update | not a fixed event | - |\n"
    )
    rc, out = _run(lab, monkeypatch, capsys)
    assert rc == 1
    assert "audit-event" in out and "'PROGRESS'" in out and "log.md:3" in out


def test_every_vocabulary_event_passes(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    events = ll._audit_events()
    assert {"GATE", "CATCH", "CRITIC_ERR", "RULING", "BUDGET", "CUT", "RETRACT"} <= events
    rows = "\n".join(
        f"| {_iso(NOW - HOUR)} | {e} | E1 | ok | - | - |" for e in sorted(events)
    )
    (lab / "audit" / "log.md").write_text(
        "| Time | Event | Experiment | Outcome | Detail | Evidence |\n"
        "|---|---|---|---|---|---|\n" + rows + "\n"
    )
    rc, out = _run(lab, monkeypatch, capsys)
    assert rc == 0, out
