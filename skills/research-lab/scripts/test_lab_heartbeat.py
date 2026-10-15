"""Tests for lab_heartbeat.py: the one-digest heartbeat.

The fixture lab is a copy of fixtures/heartbeat-lab; ages and overdue checks
are pinned with ``os.utime`` plus ``--now`` so nothing depends on the wall
clock. herdr is exercised through ``lh.herdr_json`` / ``lh.resolve_command``
fakes (the live calls are plain subprocess wrappers); the digest is otherwise
run exactly as the overseer runs it, in-process via ``main()``.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import lab_heartbeat as lh  # noqa: E402

FIXTURES = SCRIPTS / "fixtures"
FIXTURE_LAB = FIXTURES / "heartbeat-lab"
NOW = time.time()
HOUR = 3600


def _pin(path: Path, when: float) -> None:
    # whole seconds: --now parses to second precision, so fractional mtimes
    # would shave a second off every age
    when = int(when)
    os.utime(path, (when, when))


def _pin_tree(root: Path, when: float = NOW) -> None:
    for p in root.rglob("*"):
        if p.is_file():
            _pin(p, when)


def _now_str(offset_s: float = 0) -> str:
    # seconds precision: a minute-truncated --now would drift every age by up to 59s
    return datetime.fromtimestamp(NOW + offset_s).strftime("%Y-%m-%d %H:%M:%S")


def _hhmm(offset_s: float = 0) -> str:
    return datetime.fromtimestamp(NOW + offset_s).strftime("%H:%M")


def _make_lab(tmp_path: Path) -> Path:
    lab = tmp_path / "lab"
    shutil.copytree(FIXTURE_LAB, lab)
    _pin_tree(lab)
    return lab


def _fresh_milestones(lab: Path) -> None:
    """Milestones due later today (or tomorrow) so the clean path cannot flake."""
    _pin(lab / "status.md", NOW)
    (lab / "status.md").write_text(
        "Lab running: 0/1 experiments decided, no blockers.\n\n"
        "| by | milestone | state |\n|---|---|---|\n"
        f"| {_hhmm(2 * HOUR)} | page audited | [ ] |\n"
        f"| {_hhmm(3 * HOUR)} | final report sent | [ ] |\n\n"
        "| id | question | tier | state | budget | eta |\n"
        "|---|---|---|---|---|---|\n"
        f"| E1 | does B dominate A? | headline | [-] | 2 h | eta {_hhmm(2 * HOUR)} |\n"
    )


def _run(lab: Path, *args: str, monkeypatch, capsys) -> tuple[int, str]:
    monkeypatch.setattr(
        sys, "argv", ["lab_heartbeat.py", str(lab), "--now", _now_str(), *args]
    )
    rc = lh.main()
    return rc, capsys.readouterr().out


def _send(lab: Path, member: str, name: str, body: str, age_s: float = 0) -> Path:
    inbox = lab / "mailbox" / "inboxes" / member
    inbox.mkdir(parents=True, exist_ok=True)
    msg = inbox / name
    msg.write_text(body)
    _pin(msg, NOW - age_s)
    return msg


def _fake_herdr(monkeypatch, *, status: str, command: str, cwd: Path) -> None:
    def fake(*args: str):
        if args[0] == "agent":
            return {"result": {"agent": {"agent_status": status, "cwd": str(cwd)}}}
        if args[0] == "pane":
            return {"result": {"process_info": {"foreground_processes": [{"argv": [command]}]}}}
        raise AssertionError(f"unexpected herdr call: {args}")

    monkeypatch.setattr(lh, "herdr_json", fake)
    monkeypatch.setattr(lh, "resolve_command", lambda role, profile: "claude --model big")


# ---- clock -------------------------------------------------------------------


def test_clean_lab_zero_flags(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out
    assert "heartbeat: 0 flag(s)" in out
    assert "clock: deadline 2099-12-31 09:00 (policy.md)" in out
    assert "clock: 0 overdue milestone(s)" in out
    assert "mail: 0 unread across 2 member(s)" in out
    assert "members: herdr checks skipped (--no-herdr)" in out
    assert "status: line 1 fresh" in out
    assert "lint: lab_lint clean" in out
    assert len(out.splitlines()) <= 15


def test_overdue_milestone_flagged(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    (lab / "status.md").write_text(
        "Lab running.\n\n"
        "| by | milestone | state |\n|---|---|---|\n"
        f"| {_hhmm(-HOUR)} | page audited | [ ] |\n\n"
        "| id | question | tier | state | budget | eta |\n"
        "|---|---|---|---|---|---|\n"
        "| E1 | q? | headline | [-] | 2 h | eta 23:00 |\n"
    )
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1
    assert 'FLAG clock: milestone "page audited" overdue' in out


def test_done_and_cut_milestones_not_overdue(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    (lab / "status.md").write_text(
        "Lab running.\n\n"
        "| by | milestone | state |\n|---|---|---|\n"
        f"| {_hhmm(-HOUR)} | page audited | [x] |\n"
        f"| {_hhmm(-HOUR)} | sweep dropped | [S] |\n\n"
        "| id | question | tier | state | budget | eta |\n"
        "|---|---|---|---|---|---|\n"
        "| E1 | q? | headline | [-] | 2 h | eta 23:00 |\n"
    )
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out


def test_deadline_relative_time(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    (lab / "policy.md").write_text(
        "# Lab policy\n\n## Time box\n\n- Deadline: " + _now_str(3 * HOUR) + "\n"
    )
    _pin(lab / "policy.md", NOW)
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out
    assert "in 3h00m" in out
    (lab / "policy.md").write_text(
        "# Lab policy\n\n## Time box\n\n- Deadline: " + _now_str(-HOUR) + "\n"
    )
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert "1h00m ago" in out  # reporting only, not a flag


def test_no_deadline(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    (lab / "policy.md").write_text("# Lab policy\n\n## Time box\n\n- Deadline: none\n")
    _pin(lab / "policy.md", NOW)
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out
    assert "clock: no deadline" in out


# ---- mail --------------------------------------------------------------------


def test_mail_blocker_flagged(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    _send(lab, "worker-1", "author.001-e1-status.msg", "E1 blocked: GPU unavailable", age_s=300)
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1
    assert "FLAG mail: worker-1 1 unread, oldest 5m, 1 blocker(s)" in out


def test_mail_older_than_period_flagged(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    _send(lab, "worker-1", "author.001-e1-status.msg", "FYI: stage 3 done", age_s=45 * 60)
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1
    assert "FLAG mail: worker-1 1 unread, oldest 45m (over the 30m period)" in out


def test_mail_fresh_not_flagged(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    _send(lab, "worker-1", "author.001-e1-status.msg", "FYI: stage 3 done", age_s=5 * 60)
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out
    assert "mail: 1 unread across 1 member(s)" in out


def test_handled_mail_excluded(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    handled = lab / "mailbox" / "inboxes" / "worker-1" / "handled"
    handled.mkdir()
    (handled / "author.001-e1-status.msg").write_text("FYI")
    _pin(handled / "author.001-e1-status.msg", NOW)
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out
    assert "mail: 0 unread across 2 member(s)" in out


# ---- members (herdr fakes) -----------------------------------------------------


def test_member_dead_flagged(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    monkeypatch.setattr(lh, "herdr_json", lambda *args: None)
    rc, out = _run(lab, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1
    assert "FLAG member: worker-1 no live agent at pane wX:p1" in out
    assert "FLAG member: lab-overseer no live agent at pane wX:p0" in out


def test_member_command_mismatch_flagged(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    _fake_herdr(monkeypatch, status="working", command="gemini", cwd=tmp_path)
    rc, out = _run(lab, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1
    assert "FLAG member: worker-1 runs 'gemini', staffing for role 'worker' says 'claude'" in out


def test_member_env_prefixed_launcher_matches(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    # real profiles gate the launcher and wrap it: the env prefix is not the
    # command, and a wrapper (local-claude) execs the real binary
    _fake_herdr(monkeypatch, status="working", command="claude", cwd=tmp_path)
    monkeypatch.setattr(
        lh, "resolve_command", lambda role, profile: "COMMIT_AUTHORISED=1 ~/.local/bin/local-claude"
    )
    rc, out = _run(lab, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out


def test_member_idle_with_unread_flagged(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    _send(lab, "worker-1", "author.001-e1-status.msg", "FYI: stage 3 done", age_s=60)
    _fake_herdr(monkeypatch, status="idle", command="claude", cwd=tmp_path)
    rc, out = _run(lab, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1
    assert "FLAG member: worker-1 idle with 1 unread" in out


def test_member_stall_flagged(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    work = tmp_path / "worker-tree"
    work.mkdir()
    (work / ".git").mkdir()
    (work / "results.md").write_text("stale")
    _pin(work / "results.md", NOW - 30 * 60)
    _pin(work, NOW - 30 * 60)
    _fake_herdr(monkeypatch, status="working", command="claude", cwd=work)
    rc, out = _run(lab, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1
    assert "possible stall" in out
    assert "30m" in out


def test_member_stall_fresh_cwd_clean(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    work = tmp_path / "worker-tree"
    work.mkdir()
    (work / "results.md").write_text("fresh")
    _pin(work / "results.md", NOW - 60)
    _fake_herdr(monkeypatch, status="working", command="claude", cwd=work)
    rc, out = _run(lab, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out
    assert "members: 2 member(s) checked, 0 flagged" in out


def test_seatless_member_skipped(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    (lab / "mailbox" / "members" / "worker-1").write_text("role=worker\n")
    _fake_herdr(monkeypatch, status="working", command="claude", cwd=tmp_path)
    rc, out = _run(lab, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out
    assert "members: 1 member(s) checked, 0 flagged" in out


# ---- status age / lint / checker ------------------------------------------------


def test_status_line1_stale_flagged(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    _pin(lab / "status.md", NOW - 2 * HOUR)
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1
    assert "FLAG status: status.md line 1 stale" in out


def test_lint_findings_flagged(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    future = lab / "experiments" / "E9.md"
    future.write_text(f"## Entry\n\nClosed {_now_str(2 * HOUR)} after the run.\n")
    _pin(future, NOW)
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1
    assert "FLAG lint: 1 lab_lint finding(s)" in out


def test_checker_failing_manifest_flagged(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    experiments = lab / "experiments"
    shutil.copy(FIXTURES / "E1_manifest_a.py", experiments / "E1_manifest_a.py")
    shutil.copy(FIXTURES / "E1_a.md", experiments / "E1_a.md")
    shutil.copy(FIXTURES / "e1_stage_timing.json", experiments / "e1_stage_timing.json")
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1
    assert "FLAG lint: checker 1/1 manifest(s) fail, E1_manifest_a" in out


def test_checker_clean_manifest(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    experiments = lab / "experiments"
    # the control manifest, renamed so it pairs with the control entry
    shutil.copy(FIXTURES / "E1_manifest.py", experiments / "E1_control_manifest.py")
    shutil.copy(FIXTURES / "E1_control.md", experiments / "E1_control.md")
    shutil.copy(FIXTURES / "e1_stage_timing.json", experiments / "e1_stage_timing.json")
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out
    assert "lint: lab_lint clean; checker 0/1 fail" in out


def test_checker_missing_experiment_flagged(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    shutil.copy(FIXTURES / "E1_manifest_a.py", lab / "experiments" / "E1_manifest_a.py")
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1
    assert "E1_manifest_a (no experiment file)" in out


def test_no_mesh(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)
    _fresh_milestones(lab)
    shutil.rmtree(lab / "mailbox")
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out
    assert "mail: no mesh" in out
    assert "members: no members" in out


# ---- worktrees -----------------------------------------------------------------


def _profile_file(tmp_path: Path, prefix: str | None = "hayden/") -> Path:
    """A PI profile fixture; prefix None writes no BRANCH_PREFIX line."""
    profile = tmp_path / "pi-profile.md"
    lines = ["TRUSTED_ROOTS: /tmp\n"]
    if prefix is not None:
        lines.append(f"BRANCH_PREFIX: {prefix}\n")
    profile.write_text("".join(lines))
    return profile


def _wt_item(branch: str, path: Path, *, dirty: bool, ahead: int | None, age_s: float) -> dict:
    changes = {
        "staged": dirty, "modified": dirty, "untracked": False,
        "renamed": False, "deleted": False, "conflicted": False,
        "diff": {"added": 2 if dirty else 0, "deleted": 0},
    }
    return {
        "branch": branch,
        "head": {
            "committed_at": datetime.fromtimestamp(NOW - age_s, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        },
        "worktree": {"path": str(path), "changes": changes},
        "upstream": {"ahead": ahead},
    }


def _lab_with_repo(tmp_path: Path, *, lab_name: str = "2026-10-15-lab-foo") -> Path:
    lab = tmp_path / lab_name
    shutil.copytree(FIXTURE_LAB, lab)
    _pin_tree(lab)
    _fresh_milestones(lab)
    (lab / "policy.md").write_text(
        (lab / "policy.md").read_text() + "\n- Code repo: /tmp/fake-repo\n"
    )
    _pin(lab / "policy.md", NOW)
    return lab


def test_worktrees_skipped_without_repo_record(tmp_path, monkeypatch, capsys):
    lab = _make_lab(tmp_path)  # no repo line, not under <repo>/.agents/work/
    _fresh_milestones(lab)
    monkeypatch.setattr(
        lh, "wt_list", lambda repo: (_ for _ in ()).throw(AssertionError("wt must not run"))
    )
    rc, out = _run(lab, "--no-herdr", monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out
    # no digest line (the tmp path itself contains 'worktrees', so match the prefix)
    assert "worktrees: " not in out


def test_worktree_digest_and_member_gone_flag(tmp_path, monkeypatch, capsys):
    lab = _lab_with_repo(tmp_path)
    profile = _profile_file(tmp_path)
    wt1, other = tmp_path / "lab-foo-tree", tmp_path / "member-cwd"
    other.mkdir()
    monkeypatch.setattr(
        lh,
        "wt_list",
        lambda repo: {
            "items": [
                _wt_item("hayden/lab-foo", wt1, dirty=True, ahead=2, age_s=3 * HOUR),
                _wt_item("hayden/lab-foo-2", tmp_path / "lab-foo-2-tree", dirty=False, ahead=0, age_s=HOUR),
                _wt_item("hayden/unrelated", tmp_path / "other-tree", dirty=True, ahead=9, age_s=HOUR),
            ]
        },
    )
    _fake_herdr(monkeypatch, status="working", command="claude", cwd=other)
    rc, out = _run(lab, "--profile", str(profile), monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 1
    assert "FLAG worktree: hayden/lab-foo dirty" in out
    assert "no live member works there" in out
    assert "worktrees: hayden/lab-foo dirty 3h00m +2; hayden/lab-foo-2 clean 1h00m +0" in out
    assert "unrelated" not in out.split("worktrees:")[1].split("\n")[0]


def test_worktree_dirty_member_present_not_flagged(tmp_path, monkeypatch, capsys):
    lab = _lab_with_repo(tmp_path)
    profile = _profile_file(tmp_path)
    wt1 = tmp_path / "lab-foo-tree"
    wt1.mkdir()
    (wt1 / "in_progress.md").write_text("wip")
    monkeypatch.setattr(
        lh,
        "wt_list",
        lambda repo: {"items": [_wt_item("hayden/lab-foo", wt1, dirty=True, ahead=1, age_s=HOUR)]},
    )
    _fake_herdr(monkeypatch, status="working", command="claude", cwd=wt1)
    rc, out = _run(lab, "--profile", str(profile), monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out
    assert "worktrees: hayden/lab-foo dirty 1h00m +1" in out


def test_worktree_dirty_without_herdr_reported_not_flagged(tmp_path, monkeypatch, capsys):
    lab = _lab_with_repo(tmp_path)
    profile = _profile_file(tmp_path)
    monkeypatch.setattr(
        lh,
        "wt_list",
        lambda repo: {"items": [_wt_item("hayden/lab-foo", tmp_path / "t", dirty=True, ahead=0, age_s=HOUR)]},
    )
    rc, out = _run(lab, "--no-herdr", "--profile", str(profile), monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out
    assert "worktrees: hayden/lab-foo dirty 1h00m +0" in out


def test_worktree_branch_prefix_from_profile(tmp_path, monkeypatch, capsys):
    lab = _lab_with_repo(tmp_path)
    profile = _profile_file(tmp_path, prefix="hp/")
    monkeypatch.setattr(
        lh,
        "wt_list",
        lambda repo: {"items": [_wt_item("hp/lab-foo", tmp_path / "t", dirty=False, ahead=0, age_s=HOUR)]},
    )
    monkeypatch.setattr(sys, "argv", [
        "lab_heartbeat.py", str(lab), "--now", _now_str(), "--no-herdr", "--profile", str(profile),
    ])
    rc = lh.main()
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "worktrees: hp/lab-foo clean 1h00m +0" in out


def test_worktree_repo_from_agents_work_parent(tmp_path, monkeypatch, capsys):
    lab = tmp_path / ".agents" / "work" / "2026-10-15-lab-bar"
    shutil.copytree(FIXTURE_LAB, lab)
    _pin_tree(lab)
    _fresh_milestones(lab)
    profile = _profile_file(tmp_path)
    seen: list[str] = []

    def fake_wt_list(repo):
        seen.append(str(repo))
        return {"items": [_wt_item("hayden/lab-bar", tmp_path / "t", dirty=False, ahead=0, age_s=HOUR)]}

    monkeypatch.setattr(lh, "wt_list", fake_wt_list)
    rc, out = _run(lab, "--no-herdr", "--profile", str(profile), monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out
    assert seen == [str(tmp_path)]  # the repo is the .agents/work parent
    assert "worktrees: hayden/lab-bar clean 1h00m +0" in out


def test_worktree_no_branch_prefix_skips(tmp_path, monkeypatch, capsys):
    lab = _lab_with_repo(tmp_path)
    # R7: no harness-default prefix - a profile without BRANCH_PREFIX and a lab
    # without a `branch` line skip the worktree section entirely
    profile = _profile_file(tmp_path, prefix=None)
    monkeypatch.setattr(
        lh,
        "wt_list",
        lambda repo: {"items": [_wt_item("hayden/lab-foo", tmp_path / "t", dirty=True, ahead=0, age_s=HOUR)]},
    )
    rc, out = _run(lab, "--no-herdr", "--profile", str(profile), monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 0, out
    assert "worktrees: " not in out
