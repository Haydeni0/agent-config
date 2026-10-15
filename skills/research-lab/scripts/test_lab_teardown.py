"""lab-teardown.sh: member tabs + files closed, safe worktrees removed; dry-run default.

Worktree state comes from `wt list --format json` (stubbed): dirty worktrees are
kept and reported; clean ones are removed via `wt remove --foreground`, which
keeps unmerged branches (the provenance records) by design.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).with_name("lab-teardown.sh")
FIXTURE_LAB = Path(__file__).with_name("fixtures") / "lab-teardown"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def f(tmp_path: Path, shims) -> SimpleNamespace:
    """A lab whose status names one real repo and three stubbed worktrees of it."""
    repo = tmp_path / "code"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "base.txt").write_text("base\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")

    worktrees = {}
    for name in ("lab-merged", "lab-prov", "lab-dirty"):
        path = tmp_path / f"wt-{name}"
        path.mkdir()
        worktrees[name] = path

    def item(branch: str, path: Path, *, main: bool = False, dirty: bool = False,
             ahead: int = 0) -> dict:
        return {
            "branch": branch,
            "worktree": {"path": str(path), "main": main, "changes": {
                "staged": False, "modified": dirty, "untracked": False,
                "renamed": False, "deleted": False, "conflicted": False}},
            "default_branch": {"ahead": ahead, "behind": 0},
        }

    items = [
        item("main", repo, main=True),
        item("hayden/lab-merged", worktrees["lab-merged"]),
        item("hayden/lab-prov", worktrees["lab-prov"], ahead=2),
        item("hayden/lab-dirty", worktrees["lab-dirty"], dirty=True, ahead=1),
    ]
    key = str(repo).replace("/", "_")
    (shims.wt_json / f"{key}.json").write_text(
        json.dumps({"repo": {"default_branch": "main"}, "items": items}))

    lab = tmp_path / "lab"
    members = lab / "mailbox" / "members"
    members.mkdir(parents=True)
    for mf in (FIXTURE_LAB / "members").iterdir():
        (members / mf.name).write_text(mf.read_text())
    status = (FIXTURE_LAB / "status.template.md").read_text()
    decisions = (FIXTURE_LAB / "decisions.template.md").read_text()
    for placeholder, value in [
        ("@REPO@", repo),
        ("@WT_MERGED@", worktrees["lab-merged"]),
        ("@WT_PROV@", worktrees["lab-prov"]),
        ("@WT_DIRTY@", worktrees["lab-dirty"]),
    ]:
        status = status.replace(placeholder, str(value))
        decisions = decisions.replace(placeholder, str(value))
    (lab / "status.md").write_text(status)
    (lab / "decisions.md").write_text(decisions)
    return SimpleNamespace(lab=lab, repo=repo, worktrees=worktrees)


def test_apply_whole_lab(f, shims):
    members = f.lab / "mailbox" / "members"

    result = shims.run(SCRIPT, ["--apply", str(f.lab)])

    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "worker: closed tab wA:t3 (pane wA:p3)" in out
    assert "worker: removed member file" in out
    assert "author: closed tab wA:t4 (pane wA:p4)" in out
    assert "pi: kept (role=PI" in out
    assert "overseer: kept (pane wA:pZ is the caller's own" in out
    assert not (members / "worker").exists()
    assert not (members / "author").exists()
    assert (members / "pi").exists()
    assert (members / "overseer").exists()
    log = shims.log.read_text()
    assert "herdr tab close wA:t3" in log
    assert "herdr tab close wA:t4" in log
    assert "herdr tab close wA:t5" not in log
    assert f"wt -C {f.repo} remove --foreground hayden/lab-merged" in log
    assert f"wt -C {f.repo} remove --foreground hayden/lab-prov" in log
    assert "remove --foreground hayden/lab-dirty" not in log
    assert f"{f.worktrees['lab-dirty']}: kept (dirty" in out
    assert (f"{f.worktrees['lab-merged']}: removed worktree "
            "(branch hayden/lab-merged merged; wt deletes the branch)") in out
    assert (f"{f.worktrees['lab-prov']}: removed worktree "
            "(branch hayden/lab-prov kept (ahead 2 of main: the provenance records))") in out
    assert "main worktree kept" in out
    assert "worktrees: 2 removed, 2 kept" in out
    assert "[dry-run]" not in out


def test_dry_run_by_default(f, shims):
    members = f.lab / "mailbox" / "members"

    result = shims.run(SCRIPT, [str(f.lab)])

    assert result.returncode == 0, result.stderr
    assert "[dry-run] worker: would close tab wA:t3" in result.stdout
    assert "[dry-run] worker: would remove member file" in result.stdout
    assert f"[dry-run] {f.worktrees['lab-prov']}: would remove worktree" in result.stdout
    assert "worktrees (dry-run): 2 removable, 2 kept" in result.stdout
    log = shims.log.read_text()
    assert "tab close" not in log
    assert "wt remove" not in log
    assert all((members / m).exists() for m in ("worker", "author", "pi", "overseer"))


def test_repeated_mentions_decided_once(f, shims):
    """Two lab files cite the same worktree and paths inside the same repo; each
    worktree still gets exactly one decision line (T6 bug: 16 duplicate lines)."""
    result = shims.run(SCRIPT, [str(f.lab)])

    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert out.count(f"[dry-run] {f.worktrees['lab-prov']}: would remove worktree") == 1
    assert out.count(f"[dry-run] {f.worktrees['lab-merged']}: would remove worktree") == 1
    assert out.count(f"{f.worktrees['lab-dirty']}: kept (dirty") == 1
    assert out.count("main worktree kept") == 1
    assert "worktrees (dry-run): 2 removable, 2 kept" in out


def test_member_subset_skips_worktrees(f, shims):
    members = f.lab / "mailbox" / "members"

    result = shims.run(SCRIPT, ["--apply", str(f.lab), "worker"])

    assert result.returncode == 0, result.stderr
    assert "worker: closed tab wA:t3" in result.stdout
    assert "worktree cleanup skipped" in result.stdout
    assert not (members / "worker").exists()
    assert (members / "author").exists()
    log = shims.log.read_text()
    assert "herdr tab close wA:t3" in log
    assert "herdr tab close wA:t4" not in log
    assert "wt remove" not in log


def test_dead_pane_reported(f, shims):
    members = f.lab / "mailbox" / "members"

    result = shims.run(SCRIPT, ["--apply", str(f.lab), "author"],
                       HERDR_DEAD_PANES="wA:p4")

    assert result.returncode == 0, result.stderr
    assert "author: no live agent at wA:p4; close its tab by hand" in result.stdout
    assert not (members / "author").exists(), "member file is removed; the pane is gone either way"
    assert "tab close" not in shims.log.read_text()


def test_worktree_of_caller_kept(f, shims):
    result = shims.run(SCRIPT, ["--apply", str(f.lab)], cwd=f.worktrees["lab-prov"])

    assert result.returncode == 0, result.stderr
    assert f"{f.worktrees['lab-prov']}: kept (the caller is running in it)" in result.stdout
    assert "wt remove --foreground hayden/lab-prov" not in shims.log.read_text()


def test_unknown_member_fails(f, shims):
    result = shims.run(SCRIPT, ["--apply", str(f.lab), "ghost"])

    assert result.returncode == 1
    assert "no member file for 'ghost'" in result.stderr


def test_not_a_lab_fails(tmp_path, shims):
    empty = tmp_path / "empty"
    empty.mkdir()

    result = shims.run(SCRIPT, [str(empty)])

    assert result.returncode == 1
    assert "mailbox/members" in result.stderr