# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
# ///
"""One heartbeat digest for a running lab: everything the overseer would
otherwise check by hand each beat (SKILL.md, Start step 6), in at most ~15
lines, most urgent first. Stdlib plus the sibling checkers; deterministic and
read-only except for the child checker runs.

Sections (FLAG lines are urgent, then one summary line each):

- clock: overdue milestones from the status.md table ``| by | milestone |
  state |`` (a ``by`` of bare HH:MM means today), and time to the deadline
  (``Deadline:`` line in policy.md, else status.md).
- mail: unread files per member under ``mailbox/inboxes/<member>/``
  (``handled/`` excluded), oldest age; FLAG when a message body names a
  blocker or one is older than the heartbeat period.
- members: for each ``mailbox/members/<name>`` file with ``pane=``, the live
  herdr agent state (``herdr agent get``), the pane's actual command
  (``herdr pane process-info --pane``) vs the PI profile Staffing row
  (``spawn-member.sh --resolve <role>``). FLAG on a dead agent, a command
  mismatch, idle with unread mail, or a "working" member with no file change
  in its pane cwd for ``--stall-min`` minutes (possible stall; .git and
  similar trees are pruned from the scan).
- status: age of status.md line 1 (the PI's one-line state); FLAG when older
  than the heartbeat period.
- lint: runs lab_lint.py over the lab and lab_checker.py over every
  experiments/ manifest whose name contains ``_manifest`` paired with the
  same-name .md (``<eid>_manifest.py`` -> ``<eid>.md``, ``<x>_manifest_<y>.py``
  -> ``<x>_<y>.md``); FLAG on any finding or failing manifest.
- worktrees: the lab's code worktrees from ``wt -C <repo> list --format json``
  (branch, dirty, commits ahead, age) for branches matching the lab's branch
  prefix + lab id. The repo comes from a ``code repo`` line in policy.md or
  status.md, else the lab dir's ``<repo>/.agents/work/`` parent; the branch
  from a ``branch`` line, else ``<BRANCH_PREFIX>lab-<id>`` from the PI profile
  (no default - a profile without ``BRANCH_PREFIX:`` and a lab without a
  ``branch`` line skip the section, R7).
  FLAG on a dirty worktree whose member is gone (no live agent works there).
  Skipped silently when the lab records no repo.

herdr is called for real by default; ``--no-herdr`` (or LAB_HEARTBEAT_NO_HERDR=1)
skips every live check so the digest runs (and is tested) without herdr.

Usage:
    uv run --script lab_heartbeat.py <lab dir> [--heartbeat-min N] [--stall-min N]
                                  [--no-herdr] [--now "YYYY-MM-DD HH:MM"]

Exits 1 when anything is flagged, 0 clean, 2 on bad usage.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NoReturn

SCRIPTS = Path(__file__).resolve().parent
SPAWN_MEMBER = SCRIPTS / "spawn-member.sh"

DEFAULT_HEARTBEAT_MIN = 30
DEFAULT_STALL_MIN = 15
# FLAG lines the digest ever prints before the summary block
MAX_FLAG_LINES = 8

_DT_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{1,2}):(\d{2})(?::(\d{2}))?)?")
_HHMM_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_DEADLINE_RE = re.compile(r"^\s*[-*]?\s*deadline:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_REPO_RE = re.compile(r"(?i)\bcode repo(?:sitory)?\b[:\s`*|-]*([~/][^\s`*|,;)]+)")
_BRANCH_RE = re.compile(r"(?i)\bbranch\b[:\s`*|-]*([A-Za-z0-9._/-]+)")
# a message body naming a blocker; the mesh has no in-band marker, so the
# word is the signal (SKILL.md: "a member that is blocked sends with a ring")
_BLOCKER_RE = re.compile(r"\bblock(?:er|ed|ing)?\b", re.IGNORECASE)
# milestone state cells that cannot be overdue: done or cut
_DONE_RE = re.compile(r"\[x\]|\[S\]|done|cut", re.IGNORECASE)
# directories never scanned for member activity
_PRUNE_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".cache", ".tox"}
DEFAULT_PROFILE = "~/.config/research-lab/pi-profile.md"

_USAGE = __doc__


def fail_usage(message: str) -> NoReturn:
    print(f"{message}\n\n{_USAGE}")
    raise SystemExit(2)


@dataclass
class Flag:
    # lower = more urgent; ties keep insertion order
    sev: int
    text: str


@dataclass
class MemberMail:
    unread: int = 0
    oldest_age_s: float | None = None
    blockers: int = 0


@dataclass
class MemberLive:
    name: str
    role: str
    pane: str
    status: str | None  # herdr agent_status; None = no live agent at the pane
    cwd: Path | None
    command: str | None  # foreground process name; None = pane not running it


# ---- time helpers -----------------------------------------------------------


def parse_when(text: str, now: datetime) -> datetime | None:
    """A `by`/deadline cell: ISO date (optional time), bare HH:MM (today), or None.

    A date without a time means the end of that day - a milestone due "by
    2026-10-15" is overdue only from the 16th on.
    """
    m = _DT_RE.search(text)
    if m:
        if m.group(4) is None:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 23, 59, 59)
        return datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)), int(m.group(6) or 0),
        )
    m = _HHMM_RE.search(text)
    if m and 0 <= int(m.group(1)) <= 23:
        return now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
    return None


def fmt_age(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"
    return f"{seconds // 86400}d{seconds % 86400 // 3600}h"


# ---- clock -------------------------------------------------------------------


def find_deadline(lab: Path, now: datetime) -> tuple[datetime | None, str]:
    """The lab deadline from policy.md, else status.md; (when, source file name)."""
    for name in ("policy.md", "status.md"):
        f = lab / name
        if not f.is_file():
            continue
        m = _DEADLINE_RE.search(f.read_text(errors="replace"))
        if m and m.group(1).strip().lower() != "none":
            if _DT_RE.search(m.group(1)):
                return parse_when(m.group(1), now), name
    return None, ""


def overdue_milestones(lab: Path, now: datetime) -> list[tuple[str, str, float]]:
    """(milestone, `by` cell, seconds late) for every undone past-due milestone row."""
    status = lab / "status.md"
    if not status.is_file():
        return []
    lines = status.read_text(errors="replace").splitlines()
    out = []
    in_table = False
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and cells[:3] == ["by", "milestone", "state"]:
            in_table = True
            continue
        if in_table:
            if not line.lstrip().startswith("|"):
                in_table = False
                continue
            if set("".join(cells)) <= {"-", " ", ":"}:
                continue  # separator row: still the table
            if len(cells) >= 3 and not _DONE_RE.search(cells[2]):
                when = parse_when(cells[0], now)
                if when is not None and when < now:
                    out.append((cells[1], cells[0], (now - when).total_seconds()))
    return out


# ---- mail --------------------------------------------------------------------


def scan_mail(lab: Path, now: datetime) -> tuple[dict[str, MemberMail], bool]:
    """Unread mail per member; (per-member state, mesh exists)."""
    inboxes = lab / "mailbox" / "inboxes"
    if not inboxes.is_dir():
        return {}, False
    per_member: dict[str, MemberMail] = {}
    for inbox in sorted(inboxes.iterdir()):
        if not inbox.is_dir():
            continue
        state = MemberMail()
        for msg in sorted(inbox.iterdir()):
            # handled/ is a subdirectory, so plain files here are unread
            if not msg.is_file() or msg.name.startswith("."):
                continue
            if not re.fullmatch(
                r"[a-z0-9]+(?:-[a-z0-9]+)*\.\d+-[a-z0-9-]+\.(?:msg|reply)", msg.name
            ):
                continue
            state.unread += 1
            age = now.timestamp() - msg.stat().st_mtime
            state.oldest_age_s = age if state.oldest_age_s is None else max(state.oldest_age_s, age)
            if _BLOCKER_RE.search(msg.read_text(errors="replace")[:4000]):
                state.blockers += 1
        per_member[inbox.name] = state
    return per_member, True


# ---- members (herdr) -----------------------------------------------------------


def herdr_json(*args: str) -> dict | None:
    """One herdr call's JSON result; None on any failure (dead pane, bad JSON)."""
    proc = subprocess.run(["herdr", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


_resolve_cache: dict[str, str] = {}


def resolve_command(role: str, profile: str | None) -> str | None:
    """The staffing command for role, via spawn-member.sh --resolve (the single
    source of the Staffing table); None when the role has no row."""
    key = f"{profile}\x00{role}"
    if key in _resolve_cache:
        return _resolve_cache[key]
    env = dict(os.environ)
    if profile:
        env["RESEARCH_LAB_PROFILE"] = profile
    proc = subprocess.run(
        [str(SPAWN_MEMBER), "--resolve", role], capture_output=True, text=True, env=env
    )
    cmd = proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None
    _resolve_cache[key] = cmd
    return cmd


def read_members(lab: Path) -> list[tuple[str, str, str | None]]:
    """(name, role, pane) from mailbox/members/, sorted by name."""
    members_dir = lab / "mailbox" / "members"
    if not members_dir.is_dir():
        return []
    out = []
    for f in sorted(members_dir.iterdir()):
        if not f.is_file():
            continue
        fields = dict(
            line.split("=", 1) for line in f.read_text(errors="replace").splitlines() if "=" in line
        )
        out.append((f.name, fields.get("role", ""), fields.get("pane")))
    return out


def live_member(name: str, role: str, pane: str) -> MemberLive:
    member = MemberLive(name=name, role=role, pane=pane, status=None, cwd=None, command=None)
    data = herdr_json("agent", "get", pane)
    if data:
        agent = data.get("result", {}).get("agent", {})
        member.status = agent.get("agent_status")
        cwd = agent.get("cwd")
        member.cwd = Path(cwd) if cwd else None
    proc_info = herdr_json("pane", "process-info", "--pane", pane)
    if proc_info:
        procs = proc_info.get("result", {}).get("process_info", {}).get("foreground_processes", [])
        if procs:
            argv = procs[0].get("argv") or []
            member.command = (argv[0] if argv else procs[0].get("name")) or None
    return member


def newest_change(root: Path) -> float | None:
    """Newest mtime under root (pruned trees skipped); the dir itself when empty."""
    newest = root.stat().st_mtime
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIRS]
        for fname in filenames:
            try:
                newest = max(newest, (Path(dirpath) / fname).stat().st_mtime)
            except OSError:
                continue  # a file vanished mid-scan: the walk is advisory, not a gate
    return newest


# ---- worktrees -----------------------------------------------------------------


def wt_list(repo: Path) -> dict | None:
    """`wt -C <repo> list --format json`; None when wt fails or is absent."""
    proc = subprocess.run(
        ["wt", "-C", str(repo), "list", "--format", "json"], capture_output=True, text=True
    )
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _lab_repo(lab: Path) -> Path | None:
    """The lab's code repo: a `code repo` line in policy.md/status.md, else the
    repo whose .agents/work/ holds the lab dir."""
    for name in ("policy.md", "status.md"):
        f = lab / name
        if not f.is_file():
            continue
        m = _REPO_RE.search(f.read_text(errors="replace"))
        if m:
            return Path(os.path.expanduser(m.group(1)))
    if lab.parent.name == "work" and lab.parent.parent.name == ".agents":
        return lab.parent.parent.parent
    return None


def _branch_prefix(profile: str | None) -> str | None:
    """BRANCH_PREFIX: from the PI profile; None when the profile has none.

    No harness default - the prefix is a machine fact (R7), so a profile
    without it and a lab without a `branch` line skip the worktree section.
    """
    path = Path(os.path.expanduser(profile or os.environ.get("RESEARCH_LAB_PROFILE") or DEFAULT_PROFILE))
    try:
        text = path.read_text()
    except OSError:
        return None
    m = re.search(r"^BRANCH_PREFIX:\s*(\S+)", text, re.MULTILINE)
    return m.group(1).rstrip("/") + "/" if m else None


def _lab_branch(lab: Path, profile: str | None) -> str | None:
    """The branch token lab worktrees carry: a `branch` line in the lab files,
    else <BRANCH_PREFIX>lab-<id> from the lab dir name; None when neither
    the lab nor the profile names a branch."""
    for name in ("policy.md", "status.md"):
        f = lab / name
        if not f.is_file():
            continue
        m = _BRANCH_RE.search(f.read_text(errors="replace"))
        if m:
            return m.group(1)
    prefix = _branch_prefix(profile)
    if prefix is None:
        return None
    lab_id = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", lab.name)
    return prefix + (lab_id if lab_id.startswith("lab-") else f"lab-{lab_id}")


def _wt_dirty(item: dict) -> bool:
    changes = (item.get("worktree") or {}).get("changes") or {}
    diff = changes.get("diff") or {}
    return (
        any(changes.get(k) for k in ("staged", "modified", "untracked", "renamed", "deleted", "conflicted"))
        or bool(diff.get("added") or diff.get("deleted"))
    )


def _wt_age(item: dict, now: datetime) -> str:
    committed = (item.get("head") or {}).get("committed_at")
    if not committed:
        return "?"
    when = datetime.fromisoformat(committed.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    return fmt_age((now - when).total_seconds())


def scan_worktrees(
    lab: Path, profile: str | None, now: datetime, member_cwds: list[Path] | None
) -> tuple[str | None, list[Flag]]:
    """(summary line, flags) for the lab's code worktrees; (None, []) = skip.

    member_cwds is None when herdr checks were skipped: a dirty worktree
    cannot be judged abandoned, so it is reported without a flag.
    """
    repo = _lab_repo(lab)
    if repo is None:
        return None, []
    token = _lab_branch(lab, profile)
    if not token:
        return None, []
    data = wt_list(repo)
    if not data:
        return None, []
    matching = [it for it in data.get("items", []) if token in (it.get("branch") or "")]
    if not matching:
        return None, []
    flags: list[Flag] = []
    parts = []
    for item in matching:
        branch = item.get("branch") or "?"
        path = Path((item.get("worktree") or {}).get("path") or "")
        dirty = _wt_dirty(item)
        ahead = (item.get("upstream") or {}).get("ahead")
        parts.append(f"{branch} {'dirty' if dirty else 'clean'} {_wt_age(item, now)} +{ahead or 0}")
        if dirty and member_cwds is not None and not any(
            cwd == path or path in cwd.parents for cwd in member_cwds
        ):
            flags.append(
                Flag(3, f"worktree: {branch} dirty ({path}) but no live member works there - "
                        f"uncommitted work left behind")
            )
    summary = "; ".join(parts[:3]) + (" ..." if len(parts) > 3 else "")
    return summary, flags


# ---- lint / checker ------------------------------------------------------------


def _capture_main(module, argv: list[str]) -> tuple[int, str]:
    saved = sys.argv
    buf = io.StringIO()
    try:
        sys.argv = argv
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            rc = module.main()
    finally:
        sys.argv = saved
    return rc, buf.getvalue()


def lint_count(lab: Path) -> tuple[int | None, str]:
    """lab_lint.py findings over the lab; (None, error) when the run itself failed."""
    sys.path.insert(0, str(SCRIPTS))
    import lab_lint

    try:
        rc, out = _capture_main(lab_lint, ["lab_lint.py", str(lab)])
    except SystemExit as e:
        return None, f"lab_lint exited {e.code}"
    except Exception as e:  # noqa: BLE001 - a broken lab must not break the digest
        return None, f"lab_lint crashed: {e}"
    m = re.search(r"lab lint: (?:clean|(\d+) finding)", out)
    if rc not in (0, 1) or not m:
        return None, f"lab_lint unreadable (rc={rc})"
    return (0 if rc == 0 else int(m.group(1) or 0)), ""


def checker_pairs(lab: Path) -> list[tuple[Path, Path]]:
    """(manifest, experiment) for every experiments/*_manifest*.py with its .md."""
    experiments = lab / "experiments"
    if not experiments.is_dir():
        return []
    pairs = []
    for manifest in sorted(experiments.glob("*_manifest*.py")):
        stem = manifest.stem.replace("_manifest", "", 1)
        pairs.append((manifest, experiments / f"{stem}.md"))
    return pairs


def checker_summary(lab: Path) -> tuple[int, int, list[str]]:
    """(failing, total, names of failing manifests) via lab_checker.py per pair.

    A pair whose experiment .md is missing counts as failing - the manifest
    drifted from its entry and the critic would see an uncheckable claim.
    """
    pairs = checker_pairs(lab)
    if not pairs:
        return 0, 0, []
    sys.path.insert(0, str(SCRIPTS))
    import lab_checker

    failing, names = [], []
    for manifest, experiment in pairs:
        if not experiment.is_file():
            failing.append(manifest)
            names.append(f"{manifest.stem} (no experiment file)")
            continue
        try:
            rc, _ = _capture_main(
                lab_checker, ["lab_checker.py", str(manifest), str(experiment)]
            )
        except SystemExit as e:
            rc = int(e.code or 1)
        except Exception:  # noqa: BLE001 - a broken manifest is a failing manifest
            rc = 1
        if rc != 0:
            failing.append(manifest)
            names.append(manifest.stem)
    return len(failing), len(pairs), names


# ---- digest -------------------------------------------------------------------


def _member_flags(
    members: list[tuple[str, str, str | None]],
    mail: dict[str, MemberMail],
    now: datetime,
    stall_min: int,
    profile: str | None,
) -> tuple[list[Flag], int, list[Path]]:
    """(flags, members checked, live members' pane cwds) - the cwds feed the
    dirty-worktree-with-no-member flag."""
    flags: list[Flag] = []
    checked = 0
    cwds: list[Path] = []
    for name, role, pane in members:
        if pane is None:
            continue  # seat-less member: the mailbox audit owns that finding
        checked += 1
        m = live_member(name, role, pane)
        if m.cwd is not None:
            cwds.append(m.cwd)
        unread = mail.get(name, MemberMail()).unread
        if m.status is None:
            flags.append(Flag(1, f"member: {name} no live agent at pane {pane}"))
            continue
        if m.status == "idle" and unread:
            flags.append(Flag(3, f"member: {name} idle with {unread} unread"))
        if m.status == "working" and m.cwd and m.cwd.is_dir():
            quiet_s = now.timestamp() - (newest_change(m.cwd) or now.timestamp())
            if quiet_s > stall_min * 60:
                flags.append(
                    Flag(2, f"member: {name} working, no file change in {m.cwd} for "
                            f"{fmt_age(quiet_s)} (possible stall)")
                )
        if m.command:
            resolved = resolve_command(role or "default", profile)
            if resolved is None:
                flags.append(Flag(6, f"member: {name} role '{role}' has no staffing row"))
            else:
                # the launcher may carry shell env prefixes (VAR=value claude ...)
                expected = next(
                    (t for t in resolved.split() if not re.match(r"^[A-Za-z_]\w*=", t)),
                    resolved.split()[0],
                )
                actual, want = Path(m.command).name, Path(expected).name
                # a wrapper launcher (local-claude) execs the real binary, so a
                # suffix match is the same command; only a different binary is a flag
                if actual != want and not actual.endswith(want) and not want.endswith(actual):
                    flags.append(
                        Flag(6, f"member: {name} runs '{m.command}', staffing for role "
                                f"'{role}' says '{expected}'")
                    )
    return flags, checked, cwds


def main() -> int:
    argv = sys.argv[1:]
    opts = {
        "--heartbeat-min": DEFAULT_HEARTBEAT_MIN,
        "--stall-min": DEFAULT_STALL_MIN,
        "--now": None,
        "--profile": None,
    }
    no_herdr = os.environ.get("LAB_HEARTBEAT_NO_HERDR") == "1"
    lab_arg = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--no-herdr":
            no_herdr = True
        elif a in opts:
            i += 1
            if i >= len(argv):
                fail_usage(f"{a} needs a value")
            if a in ("--heartbeat-min", "--stall-min"):
                try:
                    opts[a] = int(argv[i])
                except ValueError:
                    fail_usage(f"{a}: not a number: {argv[i]}")
            else:
                opts[a] = argv[i]
        elif a.startswith("--") or lab_arg is not None:
            fail_usage(f"unknown or repeated argument: {a}")
        else:
            lab_arg = a
        i += 1
    if lab_arg is None:
        fail_usage("missing lab dir")
    lab = Path(lab_arg)
    if not lab.is_dir():
        print(f"not a directory: {lab}")
        return 2

    try:
        now = datetime.strptime(opts["--now"], "%Y-%m-%d %H:%M:%S") if opts["--now"] else None
    except ValueError:
        try:
            now = datetime.strptime(opts["--now"], "%Y-%m-%d %H:%M") if opts["--now"] else None
        except ValueError:
            fail_usage(f"--now: expected 'YYYY-MM-DD HH:MM': {opts['--now']}")
    if now is None:
        now = datetime.now()

    heartbeat_min: int = opts["--heartbeat-min"]
    heartbeat_s = heartbeat_min * 60
    stall_min: int = opts["--stall-min"]
    profile: str | None = opts["--profile"]

    flags: list[Flag] = []

    # mail (filesystem, always checked)
    mail, mesh = scan_mail(lab, now)
    unread_total = 0
    unread_members = 0
    for name, state in sorted(mail.items()):
        unread_total += state.unread
        unread_members += bool(state.unread)
        if not state.unread:
            continue
        age = f", oldest {fmt_age(state.oldest_age_s)}" if state.oldest_age_s is not None else ""
        if state.blockers:
            flags.append(Flag(0, f"mail: {name} {state.unread} unread{age}, {state.blockers} blocker(s)"))
        elif state.oldest_age_s is not None and state.oldest_age_s > heartbeat_s:
            flags.append(Flag(4, f"mail: {name} {state.unread} unread{age} (over the {heartbeat_min}m period)"))

    # members (herdr, skippable)
    members = read_members(lab)
    checked = 0
    member_cwds: list[Path] | None = None  # None = herdr checks skipped
    if members and not no_herdr:
        member_flags, checked, member_cwds = _member_flags(members, mail, now, stall_min, profile)
        flags.extend(member_flags)

    # worktrees (wt; skipped silently when the lab records no repo)
    wt_summary, wt_flags = scan_worktrees(lab, profile, now, member_cwds)
    flags.extend(wt_flags)

    # clock
    deadline, deadline_src = find_deadline(lab, now)
    overdue = overdue_milestones(lab, now)
    for milestone, by, late_s in overdue:
        flags.append(Flag(5, f'clock: milestone "{milestone}" overdue {fmt_age(late_s)} (by {by})'))

    # status.md line 1 age
    status_fresh = True
    status = lab / "status.md"
    status_age = None
    if not status.is_file():
        flags.append(Flag(7, "status: status.md missing"))
        status_fresh = False
    else:
        status_age = now.timestamp() - status.stat().st_mtime
        status_fresh = status_age <= heartbeat_s

    # lint + checker
    lint_n, lint_err = lint_count(lab)
    checker_fail, checker_total, checker_names = checker_summary(lab)

    if lint_n is None:
        flags.append(Flag(7, f"lint: {lint_err}"))
    elif lint_n:
        flags.append(Flag(7, f"lint: {lint_n} lab_lint finding(s)"))
    if checker_fail:
        detail = f", {', '.join(checker_names[:3])}" + (", ..." if len(checker_names) > 3 else "")
        flags.append(Flag(7, f"lint: checker {checker_fail}/{checker_total} manifest(s) fail{detail}"))

    if not status_fresh and status_age is not None:
        flags.append(Flag(7, f"status: status.md line 1 stale {fmt_age(status_age)}"))

    # ---- print, most urgent first, capped so the digest stays one screen ----
    flags.sort(key=lambda f: f.sev)
    print(f"lab heartbeat {lab} at {now.strftime('%Y-%m-%d %H:%M')}")
    shown, hidden = 0, 0
    for f in flags:
        if shown >= MAX_FLAG_LINES:
            hidden += 1
            continue
        print(f"FLAG {f.text}")
        shown += 1
    if hidden:
        print(f"... +{hidden} more flag(s)")

    if deadline is not None:
        delta = (deadline - now).total_seconds()
        where = "in " + fmt_age(delta) if delta >= 0 else fmt_age(-delta) + " ago"
        print(f"clock: deadline {deadline.strftime('%Y-%m-%d %H:%M')} ({deadline_src}), {where}")
    else:
        print("clock: no deadline")
    print(f"clock: {len(overdue)} overdue milestone(s)")
    if not mesh:
        print("mail: no mesh")
    elif unread_total:
        print(f"mail: {unread_total} unread across {unread_members} member(s)")
    else:
        print(f"mail: 0 unread across {len(mail)} member(s)")
    if not members:
        print("members: no members")
    elif no_herdr:
        print("members: herdr checks skipped (--no-herdr)")
    else:
        flagged_members = sum(1 for f in flags if f.text.startswith("member: "))
        print(f"members: {checked} member(s) checked, {flagged_members} flagged")
    if wt_summary is not None:
        print(f"worktrees: {wt_summary}")
    if not status.is_file():
        print("status: status.md missing")
    else:
        print(f"status: line 1 {'fresh' if status_fresh else 'stale'}"
              + (f" ({fmt_age(status_age)})" if status_age is not None else ""))
    if lint_n is None:
        print(f"lint: lab_lint did not run ({lint_err})")
    else:
        lint_bits = [f"lab_lint {'clean' if lint_n == 0 else f'{lint_n} finding(s)'}"]
        if checker_total:
            lint_bits.append(f"checker {checker_fail}/{checker_total} fail")
        print(f"lint: {'; '.join(lint_bits)}")
    print(f"heartbeat: {len(flags)} flag(s)")
    return 1 if flags else 0


if __name__ == "__main__":
    sys.exit(main())
