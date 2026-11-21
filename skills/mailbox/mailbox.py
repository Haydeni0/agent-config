#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12"]
# ///
"""File mailbox linking running agent sessions in herdr panes.

Layout under the mailbox root: README.md (the contract), bin/mailbox (this
script, copied by `init`), members/<name> (`role=`, plus the seat the member
joined from - `pane=`, `session=`, `harness=`, `harness-session=` - as herdr
reports them, and for spawned members `launcher=`, `spawned-by=`, `tab=`),
inboxes/<name>/ (unread files), inboxes/<name>/inflight/
(printed but unacked - a crashed turn's mail waits here for its replay),
inboxes/<name>/handled/ (acked files), retired/ (retired members' records),
launchers.toml (the user-written allowlist of commands that may start an
agent), heartbeat.toml (the opt-in stall-watchdog policy; absent = off),
heartbeat.lock and heartbeat-state.json (the watchdog's liveness and state),
and log.jsonl (the append-only trace of joins, sends, replies, takes, acks,
control verbs and heartbeat firings). A member's name is mesh-local, not its
herdr agent name: identity is the recorded seat pane plus the harness
session, so one pane may hold different names in different meshes. Requests
are `<from>.<seq>-<slug>.msg`; a reply reuses the request id as
`<from>.<id>.reply`.
"""

import contextlib
import fcntl
import json
import os
import re
import select
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

# `.` separates filename fields, so names and slugs must never contain one
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# what agents type for a request: `7`, `007`, `007-review-api`, or its (prefixed) filename
REQUEST_REF_RE = re.compile(
    r"^(?:[a-z0-9]+(?:-[a-z0-9]+)*\.)?(?P<seq>\d+)(?:-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*))?(?:\.msg)?$"
)
ONE_REPLY_PER_REQUEST = (
    "one reply per request id - for a second report, send a new message whose slug references the request id, "
    "with a delta body, not a duplicate"
)
# reply answers a request someone sent you; everything else - following up on
# your own request, answering a reply - is a new send whose slug references
# the request id. The refusals say it outright, so a compacted session
# re-learns it from the error instead of trial and error.
FOLLOW_UP_SEND = (
    "to follow up on or report against a request of your own - or to answer a reply - "
    'send a new message whose slug references the request id: bin/mailbox send re-<seq>-<what> <to>'
)
# `<from>.<seq>-<slug>.<kind>`; groups mirror NAME_RE
MESSAGE_RE = re.compile(
    r"^(?P<sender>[a-z0-9]+(?:-[a-z0-9]+)*)\.(?P<seq>\d+)-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.(?P<kind>msg|reply)$"
)
NO_MAIL = "no unread mail"
NO_UNACKED = "no unacked mail"
# zero-padded so `ls` lists one sender's requests in send order (invariant
# holds below 1000 sends per sender - `"1000-"` sorts before `"999-"`)
SEQ_WIDTH = 3
# the `ring` verb's default idle wait: long enough to catch a turn that is
# finishing, short enough not to stall the caller's own turn; a claude seat
# still busy past it is prompted mid-turn anyway (see ring_seat)
RING_WAIT_MS = 30_000
# mail rings (send, reply, poke) wait for no idle state: a busy recipient
# holds the sender only for the guard reads and the readback - a claude
# recipient is prompted mid-turn anyway, and a busy other-harness recipient
# is left to its own inbox check, so an idle wait would tax the sender
# (14% of sampled lab sends held 81% of its send-seconds blocked on it,
# row G538) without changing what lands (see ring_seat)
MAIL_RING_WAIT_MS = 0
# the post-send readback's poll budget, 0.5 s apart: the 5 s cap of the landed
# control verbs' own readback spine (bin/lab-control.sh its post_send_readback,
# row R140), which the ring twins so a vanished line names itself at the send
RING_READBACK_POLLS = 10
TEMPLATE = Path(__file__).resolve().parent / "README.template.md"

# The helper's version. `YYYY-MM-DD.NN`, revision zero-padded; comparison parses
# (date, revision) tuples, never strings. Bump the revision in the same commit
# as any behavior change - a forgotten bump makes `update` report a changed
# helper as current (the accepted residual, D8).
MAILBOX_VERSION = "2026-11-21.01"
VERSION_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\.(?P<rev>\d{2})$")
Version = tuple[str, int]


def parse_version(text: str, path: Path) -> Version:
    match = VERSION_RE.fullmatch(text)
    if match is None:
        fail(f"{path} carries MAILBOX_VERSION {text!r}, which is not `YYYY-MM-DD.NN`; refusing to order it")
    return match["date"], int(match["rev"])


VERSION_LINE_RE = re.compile(r"^\s*MAILBOX_VERSION\s*=\s*(?P<rhs>.+?)\s*$")


def read_version(script: Path) -> Version | None:
    """The version a helper copy carries, text-parsed (never imported); None = pre-stamp."""
    for line in script.read_text().splitlines():
        match = VERSION_LINE_RE.match(line)
        if match is None:
            continue
        rhs = match["rhs"]
        # a present constant in the wrong shape is hand-edited bytes - a loud
        # refusal, never a silent pre-stamp (which would overwrite it)
        if not (len(rhs) >= 2 and rhs.startswith('"') and rhs.endswith('"')):
            fail(f"{script} carries MAILBOX_VERSION {rhs!r}, not a double-quoted value; refusing to order it")
        return parse_version(rhs[1:-1], script)
    return None


def format_version(version: Version) -> str:
    return f"{version[0]}.{version[1]:02d}"

app = typer.Typer(no_args_is_help=True, add_completion=False, invoke_without_command=True)


def fail(message: str) -> NoReturn:
    typer.echo(f"mailbox: {message}", err=True)
    raise typer.Exit(1)


class HerdrError(Exception):
    def __init__(self, command: tuple[str, ...], proc: subprocess.CompletedProcess[str]) -> None:
        try:
            # herdr reports failures as JSON on stderr; stdout stays empty on a failed call
            error = json.loads(proc.stderr or proc.stdout)["error"]
            self.code: str = error["code"]
            detail = error["message"]
        except (json.JSONDecodeError, KeyError, TypeError):
            self.code = "unparsed"
            detail = f"stdout={proc.stdout[:500]!r} stderr={proc.stderr[:500]!r}"
        super().__init__(f"herdr {' '.join(command)} failed (rc={proc.returncode}, code={self.code}): {detail}")


def herdr(*command: str) -> str:
    proc = subprocess.run(["herdr", *command], capture_output=True, text=True)
    if proc.returncode != 0:
        raise HerdrError(command, proc)
    return proc.stdout


def agent_record(name: str) -> dict[str, Any]:
    """The live herdr agent record for NAME (pane id, harness session id), or {} when no agent has it."""
    try:
        output = herdr("agent", "get", name)
    except HerdrError as exc:
        if exc.code == "agent_not_found":
            return {}
        raise
    return json.loads(output)["result"]["agent"]


def agent_record_for_pane(pane: str) -> dict[str, Any]:
    """The live herdr agent record for the agent in PANE (herdr accepts pane ids), or {} when no agent runs there."""
    try:
        output = herdr("agent", "get", pane)
    except HerdrError as exc:
        if exc.code == "agent_not_found":
            return {}
        raise
    return json.loads(output)["result"]["agent"]


def live_pane(name: str) -> str | None:
    """Pane of the live herdr agent called `name`, or None when no agent has it."""
    pane = agent_record(name).get("pane_id")
    return pane if isinstance(pane, str) else None


def own_pane() -> str:
    pane = os.environ.get("HERDR_PANE_ID")
    if not pane:
        fail("HERDR_PANE_ID is unset; run this from an agent session inside a herdr pane")
    return pane


def own_session() -> str:
    session = os.environ.get("HERDR_SESSION")
    if not session:
        fail("HERDR_SESSION is unset; run this from an agent session inside a herdr pane")
    return session


@dataclass(frozen=True, slots=True)
class Seat:
    """Where a member's session runs. Pane ids are unique only within one herdr session."""

    pane: str
    session: str


def own_seat() -> Seat:
    return Seat(pane=own_pane(), session=own_session())


@dataclass(frozen=True, slots=True)
class Member:
    name: str
    role: str
    seat: Seat | None  # None once a later join from the same seat took it over
    harness: str | None  # e.g. `claude` - a session id is untraceable without its harness
    harness_session: str | None  # the agent's own session id, when herdr knows it
    launcher: str | None  # the launchers.toml id this member was spawned through
    spawned_by: str | None  # the member that spawned this one, when it was spawned
    tab: str | None  # the herdr tab id of a spawned member, used by retire


# names that can never be members: `heartbeat` is the watchdog's reserved sender
RESERVED_NAMES = ("heartbeat",)


def member_file_problem(fields: dict[str, str]) -> str | None:
    """Why these member-file fields are unusable, or None; the loud verbs and the update audit share it."""
    if "role" not in fields:
        return "has no role= line"
    if "pane" in fields and "session" not in fields:
        return "claims pane= without session="
    return None


def read_member(path: Path) -> Member:
    fields = {key: value for key, _, value in (line.partition("=") for line in path.read_text().splitlines())}
    problem = member_file_problem(fields)
    if problem is not None:
        fail(f"member file {path} {problem}; fix it or delete the file and re-join")
    seat = Seat(pane=fields["pane"], session=fields["session"]) if "pane" in fields else None
    return Member(
        name=path.name,
        role=fields["role"],
        seat=seat,
        harness=fields.get("harness"),
        harness_session=fields.get("harness-session"),
        launcher=fields.get("launcher"),
        spawned_by=fields.get("spawned-by"),
        tab=fields.get("tab"),
    )


def write_member(root: Path, member: Member) -> None:
    lines = [f"role={member.role}"]
    if member.seat is not None:
        lines += [f"pane={member.seat.pane}", f"session={member.seat.session}"]
    if member.harness is not None:
        lines.append(f"harness={member.harness}")
    if member.harness_session is not None:
        lines.append(f"harness-session={member.harness_session}")
    if member.launcher is not None:
        lines.append(f"launcher={member.launcher}")
    if member.spawned_by is not None:
        lines.append(f"spawned-by={member.spawned_by}")
    if member.tab is not None:
        lines.append(f"tab={member.tab}")
    write_atomic(root / "members" / member.name, "\n".join(lines) + "\n")


def members(root: Path) -> list[Member]:
    return [read_member(path) for path in sorted((root / "members").iterdir())]


def live_claim(member: Member) -> tuple[bool, str | None]:
    """(claim is live, live harness session) at MEMBER's recorded seat.

    A stale claim - the pane now runs a different session, or the member is
    seat-less - is (False, None); a live claim whose session herdr cannot
    report is (True, None)."""
    if member.seat is None:
        return False, None
    if member.harness_session is not None:
        record = agent_record_for_pane(member.seat.pane)
        session = (record.get("agent_session") or {}).get("value")
        return session == member.harness_session, session
    # legacy member file (joined before harness sessions were recorded): the
    # recorded pane is the anchor. The join of its day renamed the pane to
    # the member name, but a later rename or a hand-run pane breaks that
    # name while the seat lives - the herdr name is a display nicety, never
    # the liveness check (row G871's founding shape: a live seat read as
    # offline because the name lookup missed)
    record = agent_record_for_pane(member.seat.pane)
    if not record:
        return False, None
    return True, (record.get("agent_session") or {}).get("value")


def mesh_root_if_any() -> Path | None:
    """The mesh root when this script runs as a mesh's bin/mailbox copy; None
    for the bare skill checkout, which holds no member records to resolve by."""
    root = Path(__file__).resolve().parent.parent
    if (root / "README.md").is_file() and (root / "members").is_dir():
        return root
    return None


def mailbox_root() -> Path:
    root = mesh_root_if_any()
    if root is None:
        fail(
            f"{Path(__file__).resolve().parent.parent} is not an initialised mailbox; call this "
            "script as <mailbox>/bin/mailbox (create a mailbox with `mailbox.py init <dir>` "
            "from the mailbox skill)"
        )
    return root


def check_token(value: str, what: str) -> None:
    if not NAME_RE.fullmatch(value):
        fail(f"{what} {value!r} must be lowercase letters, digits and single hyphens (it becomes part of a filename)")


@app.callback()
def _root(version: Annotated[bool, typer.Option("--version", help="Print this helper's version and exit")] = False) -> None:
    if version:
        found = read_version(Path(__file__).resolve())
        if found is None:
            fail(f"{Path(__file__).resolve()} carries no MAILBOX_VERSION line; it cannot self-report")
        typer.echo(format_version(found))
        raise typer.Exit()


@app.command()
def init(directory: Path) -> None:
    """Create a mailbox at DIRECTORY and install this helper as its bin/mailbox."""
    if not TEMPLATE.is_file():
        fail(f"{TEMPLATE} is missing - run init from the skill source, not from a mesh's bin/ copy")
    root = directory.resolve()
    if root.exists() and any(root.iterdir()):
        fail(f"{root} exists and is not empty; pick a fresh mailbox directory")
    for sub in ("members", "inboxes", "bin"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(TEMPLATE.read_text().replace("{{MAILBOX}}", str(root)))
    helper = root / "bin" / "mailbox"
    shutil.copyfile(Path(__file__).resolve(), helper)
    helper.chmod(0o755)
    typer.echo(f"mailbox ready at {root}; members join with: {helper} join <name> --role <role>")


@app.command()
def join(
    name: str,
    role: Annotated[str, typer.Option(help="Free text, e.g. planner")],
    launcher: Annotated[str | None, typer.Option(help="The launchers.toml id this member was spawned through")] = None,
    spawned_by: Annotated[str | None, typer.Option(help="The member that spawned this one")] = None,
    tab: Annotated[str | None, typer.Option(help="The herdr tab id of this member's pane")] = None,
) -> None:
    """Join the mesh as NAME: write the member file, create the inbox, name this pane's herdr agent when it has none."""
    root = mailbox_root()
    check_token(name, "name")
    if name in RESERVED_NAMES:
        fail(f"{name!r} is a reserved name - it can never be a member")
    if "\n" in role or "\r" in role:
        fail("role must be a single line - it becomes a line in the member file")
    if launcher is not None:
        launchers = load_launchers(root, required=True)
        if launcher not in launchers:
            fail(f"launcher {launcher!r} is not in {root / 'launchers.toml'}; known: {sorted(launchers)}")
    if spawned_by is not None:
        check_members(root, [spawned_by])
        if spawned_by == name:
            fail("spawned-by cannot name the member itself")
    if tab is not None:
        if not tab or "\n" in tab or "\r" in tab or any(ch.isspace() for ch in tab):
            fail(f"tab {tab!r} must be a single herdr tab id with no whitespace")
    seat = own_seat()
    record = agent_record_for_pane(seat.pane)
    for other in members(root):
        # mesh-local collision: another member of THIS mesh holds the name with a live claim
        if other.name == name and other.seat is not None and other.seat != seat and live_claim(other)[0]:
            fail(f"name {name!r} is held by the live member in pane {other.seat.pane}; pick another name")
    if not record:
        # display only: herdr names are global to the herdr session, so name an
        # unnamed pane and never steal or overwrite an existing name
        holder = live_pane(name)
        if holder is None or holder == seat.pane:
            herdr("agent", "rename", seat.pane, name)
            record = agent_record_for_pane(seat.pane)
    (root / "inboxes" / name / "handled").mkdir(parents=True, exist_ok=True)
    for other in members(root):
        # a re-join under a new name must not leave the old name claiming this seat
        if other.name != name and other.seat == seat:
            write_member(root, replace(other, seat=None))
    harness_session = (record.get("agent_session") or {}).get("value")
    write_member(
        root,
        Member(
            name=name,
            role=role,
            seat=seat,
            harness=record.get("agent"),
            harness_session=harness_session,
            launcher=launcher,
            spawned_by=spawned_by,
            tab=tab,
        ),
    )
    log_event(root, event="join", member=name, pane=seat.pane, session=harness_session)
    typer.echo(f"joined as {name}; your inbox is {root / 'inboxes' / name}")
    typer.echo(f"contract: {root / 'README.md'} - read it and follow it for the rest of this session")


class Kind(StrEnum):
    MSG = "msg"
    REPLY = "reply"


@dataclass(frozen=True, slots=True)
class Message:
    path: Path
    sender: str
    seq: int
    slug: str
    msg_id: str  # `<seq>-<slug>` exactly as in the filename, zero padding kept
    kind: Kind


def parse_message(path: Path) -> Message | None:
    """The message PATH names, or None when the file is not a mailbox message."""
    match = MESSAGE_RE.fullmatch(path.name)
    if match is None:
        return None
    return Message(
        path=path,
        sender=match["sender"],
        seq=int(match["seq"]),
        slug=match["slug"],
        msg_id=f"{match['seq']}-{match['slug']}",
        kind=Kind(match["kind"]),
    )


def messages_in(directory: Path, *, strict: bool = True) -> list[Message]:
    """Messages directly in DIRECTORY in `ls` order; `.`-prefixed in-flight writes are skipped.

    Strict (inbox, take): a foreign file is a loud failure. Lenient (status,
    poke): one member's stray file must not hide every member's counts."""
    if not directory.is_dir():
        return []
    messages = []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        message = parse_message(path)
        if message is None:
            if strict:
                fail(f"{path} is not a mailbox message (<from>.<seq>-<slug>.msg|reply); move it out of the inbox")
            continue
        messages.append(message)
    return messages


def describe(message: Message) -> str:
    return f"{message.msg_id}  from {message.sender}  {message.kind}  {message.path.stat().st_size} B"


@dataclass(frozen=True, slots=True)
class PendingRequest:
    msg_id: str
    to: tuple[str, ...]


def pending_by_member(root: Path) -> dict[str, list[PendingRequest]]:
    """Each member's sent requests with no reply yet - derived, never stored, so
    a compacted or restarted session re-learns its outstanding set from disk.

    A request is answered by any reply sharing its id whose `to` names the
    request's sender, keyed (sender, id) so two senders drawing the same seq
    never retire each other; a `closed` event answers it the same way (the
    recipient's report that no reply is coming - close, or send's auto-close
    on a `re-<seq>` slug); a reply file in the sender's box (unread,
    inflight or handled) answers it too, covering a crash between a reply
    landing and its log line. Malformed log lines are skipped: status is the
    lenient verb."""
    requests: dict[tuple[str, str], tuple[str, ...]] = {}  # (sender, id) -> to
    answered: set[tuple[str, str]] = set()
    log = root / "log.jsonl"
    if log.is_file():
        for line in log.read_text().splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("event")
            if kind == "sent":
                sender, msg_id = event.get("sender"), event.get("id")
                to = event.get("to")
                if not (isinstance(sender, str) and isinstance(msg_id, str) and isinstance(to, list) and to):
                    continue
                if event.get("kind") == "msg":
                    requests[(sender, msg_id)] = tuple(str(name) for name in to)
                elif event.get("kind") == "reply":
                    answered.add((str(to[0]), msg_id))
            elif kind == "closed":
                msg_id, to = event.get("id"), event.get("to")
                if isinstance(msg_id, str) and isinstance(to, list) and to:
                    answered.add((str(to[0]), msg_id))
    pending: dict[str, list[PendingRequest]] = {}
    for (sender, msg_id), to in requests.items():
        if (sender, msg_id) in answered:
            continue
        box = root / "inboxes" / sender
        # the dot before the id anchors the match: `.1-x.reply` never hits `.01-x.reply`
        if any(path.name.endswith(f".{msg_id}.reply")
               for directory in (box, box / "inflight", box / "handled")
               for path in directory.glob("*.reply")):
            continue
        pending.setdefault(sender, []).append(PendingRequest(msg_id=msg_id, to=to))
    return pending


class RingOutcome(StrEnum):
    RUNG = "rung"
    QUEUED = "rung: queued-unverified; the line sits in the recipient's pane until its turn reads it"
    ABSENT = "not rung: the sent line left no trace in the recipient's pane"
    NOT_IDLE = "not rung: recipient not idle and mid-turn prompting is unverified for its harness; the file waits in its inbox"
    BLOCKED = "not rung: at a permission prompt; the file waits in its inbox"
    OFFLINE = "not rung: no live herdr agent at the member's seat - tell the user; a session joining under it drains the inbox"
    TYPING = "not rung: unsubmitted typing sits in the recipient's composer - the file waits in its inbox"
    COMPOSER_UNSEEN = (
        "not rung: the recipient's composer could not be seen (menu, overlay, or herdr without"
        " `pane read --source visible`) - the file waits in its inbox"
    )


# herdr error codes that mean "leave the file for the receiver's own inbox check".
# `timeout` is not here: it means different things per verb (a busy recipient on
# wait, a slow prompt on prompt) and is handled where it can be attributed.
UNRUNG = {
    "agent_blocked": RingOutcome.BLOCKED,
    "agent_not_found": RingOutcome.OFFLINE,
}

RingFlag = Annotated[bool, typer.Option("--ring/--no-ring", help="Wake the recipient now; --no-ring is for replies and FYI mail only - requests must ring")]


def own_name(root: Path) -> str:
    seat = own_seat()
    rejoin = f"{root / 'bin' / 'mailbox'} join <name> --role <role>"
    claimants = [member.name for member in members(root) if member.seat == seat]
    if len(claimants) > 1:
        fail(f"pane {seat.pane} (herdr session {seat.session}) is claimed by several member files {claimants}; settle it with {rejoin}")
    if not claimants:
        fail(f"pane {seat.pane} is not a joined member; run {rejoin} first")
    return claimants[0]


def member_named(root: Path, name: str) -> Member | None:
    return next((m for m in members(root) if m.name == name), None)


def verified_own_name(root: Path) -> str:
    """own_name, cross-checked against the live agent in this pane: a recorded seat can outlive its agent."""
    name = own_name(root)
    member = member_named(root, name)
    rejoin = f"re-join with {root / 'bin' / 'mailbox'} join <name> --role <role> before taking mail"
    if member is None or member.seat is None:
        return name  # own_name already guarantees a seated claim
    live, live_session = live_claim(member)
    if not live:
        if member.harness_session is not None:
            fail(
                f"member file {name!r} records harness session {member.harness_session}, but the live "
                f"agent in pane {member.seat.pane} is {live_session or 'sessionless'} - a stale claim; {rejoin}"
            )
        fail(
            f"member file {name!r} claims pane {member.seat.pane}, but no live herdr agent matches its "
            f"claim - a stale claim; {rejoin}"
        )
    return name


def check_members(root: Path, names: list[str]) -> None:
    members = sorted(p.name for p in (root / "members").iterdir())
    unknown = [name for name in names if name not in members]
    if unknown:
        fail(f"not mesh members: {unknown}; members are {members}")


def read_body() -> str:
    body = sys.stdin.read()
    if not body.strip():
        fail("message body is empty; pass it on stdin")
    return body


def next_seq(root: Path, sender: str) -> int:
    # scan-then-write: two concurrent sends from one member can draw the same
    # seq; to a shared recipient the second send then fails loudly on the
    # exists-or-handled check, to disjoint recipients both land (accepted)
    pattern = re.compile(rf"^{re.escape(sender)}\.(\d+)-")
    seqs = (int(m.group(1)) for p in root.glob("inboxes/*/**/*.msg") if (m := pattern.match(p.name)))
    return max(seqs, default=0) + 1


def write_atomic(path: Path, body: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(body)
    os.replace(tmp, path)


def log_event(root: Path, **event: object) -> None:
    """Append one JSON line to the mesh trace; message files stay payload-pure."""
    line = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **event}
    with (root / "log.jsonl").open("a") as log:
        log.write(json.dumps(line) + "\n")


def write_messages(root: Path, sender: str, msg_id: str, kind: Kind, body: str, recipients: list[str]) -> dict[str, Path]:
    paths = {name: root / "inboxes" / name / f"{sender}.{msg_id}.{kind}" for name in recipients}
    # inflight counts as taken too: a reply still awaiting its ack is just as
    # answered as a handled one, so the one-reply-per-request refusal covers it
    taken = [str(p) for p in paths.values()
             if p.exists() or (p.parent / "inflight" / p.name).exists() or (p.parent / "handled" / p.name).exists()]
    if taken:
        hint = ""
        if kind is Kind.REPLY:
            hint = (f"; {ONE_REPLY_PER_REQUEST} - {FOLLOW_UP_SEND}, "
                    "or close the request if no further report is needed: bin/mailbox close <id> <from>")
        fail(f"refusing to overwrite existing message files: {taken}{hint}")
    for path in paths.values():
        write_atomic(path, body)
    return paths


def wake_line(root: Path, name: str) -> str:
    # the README always sits two levels up from the inbox; a second absolute
    # path doubles the tokens the recipient reads (and pays) on every ring
    return f": mail waiting in {root}/inboxes/{name}/ - contract: ../../README.md"


def recipient_harness(pane: str) -> str:
    """Harness of the live herdr agent in PANE, e.g. `claude`."""
    return agent_record_for_pane(pane).get("agent", "")


PROMPT_CURSOR = "❯"


def is_horizontal_rule(line: str) -> bool:
    """herdr's own rule semantic (detect/manifest.rs): a bare run of the
    box-drawing dash is a rule at any length, and a run of three or more still
    is when text follows it."""
    trimmed = line.strip()
    width = len(trimmed) - len(trimmed.lstrip("─"))
    if width == 0:
        return False
    return trimmed[width:].strip() == "" or width >= 3


# a CSI escape sequence: herdr's styled pane reads interleave them with the
# text; SGR sequences (final byte m) carry the rendering attributes
ANSI_CSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def row_text_and_dim(row: str) -> tuple[str, list[bool], list[bool]]:
    """The row's text with its ANSI sequences stripped, plus a dim flag and a
    reverse-video flag per kept character. claude renders its own
    empty-composer suggestions - a fresh session's `Try "..."` hint, a worked
    session's replay of a prior prompt - dim (SGR 2) and a human's typed draft
    plain (the probe's captured bytes), so the flags tell suggestion text from
    typed text where style-stripped text cannot. The reverse flag (SGR 7)
    carries cursor-agent's reverse-video cursor letter and space cursor."""
    chars: list[str] = []
    dims: list[bool] = []
    revs: list[bool] = []
    dim = False
    rev = False
    pos = 0
    for seq in ANSI_CSI.finditer(row):
        chars.extend(row[pos:seq.start()])
        dims.extend([dim] * (seq.start() - pos))
        revs.extend([rev] * (seq.start() - pos))
        if seq.group().endswith("m"):
            params = seq.group()[2:-1].split(";")
            i = 0
            while i < len(params):
                code = params[i]
                i += 1
                if code in ("38", "48") and i < len(params):
                    # an SGR color's own arguments: 38/48;5;N and 38/48;2;R;G;B
                    # - the colorspace's 2 is not the dim attribute, and the
                    # skip must consume mode+3 for 2 (mode+1 for 5) counted
                    # from the mode param, or the blue component parses as an
                    # attribute code - a blue of 2 or 7 would flip dim or rev
                    i += 4 if params[i] == "2" else 2 if params[i] == "5" else 0
                elif code in ("0", "00"):
                    dim = False
                    rev = False
                elif code == "2":
                    dim = True
                elif code == "22":
                    dim = False
                elif code == "7":
                    rev = True
                elif code == "27":
                    rev = False
        pos = seq.end()
    chars.extend(row[pos:])
    dims.extend([dim] * (len(row) - pos))
    revs.extend([rev] * (len(row) - pos))
    return "".join(chars), dims, revs


def claude_prompt_box_state(screen: str) -> str | None:
    """The claude composer as the pane's styled bytes show it: "empty",
    "typing", or None when the box cannot be seen - never a guess.

    The composer is the box whose top border is the second horizontal rule
    from the bottom of the pane read; its body runs to the next
    rule. A body beyond the bare prompt cursor is unsubmitted typing - a human
    draft, since an agent mid-turn does not leave one on an idle pane - unless
    every character of it renders dim: claude's own empty-composer suggestions
    render dim while a typed draft renders plain, so the dim flag is what
    tells a suggestion from a human's text."""
    lines = screen.splitlines()
    rules = [i for i, line in enumerate(lines) if is_horizontal_rule(ANSI_CSI.sub("", line))]
    if len(rules) < 2:
        return None
    for line in lines[rules[-2] + 1:]:
        if is_horizontal_rule(ANSI_CSI.sub("", line)):
            break
        text, dims, _ = row_text_and_dim(line)
        if text.startswith(PROMPT_CURSOR):
            text = text[len(PROMPT_CURSOR):]
            dims = dims[len(PROMPT_CURSOR):]
        if not text.strip():
            continue
        if all(dim for dim, ch in zip(dims, text) if ch.strip()):
            continue
        return "typing"
    return "empty"


CURSOR_PROMPT_GLYPH = "→"
TRUECOLOR_BG = re.compile(r"\x1b\[48;2;(\d+;\d+;\d+)m")


def cursor_prompt_box_state(screen: str) -> str | None:
    """The cursor-agent composer as the pane's styled bytes show it: "empty",
    "typing", or None when the box cannot be seen - never a guess.

    The composer is the box of contiguous rows sharing one exact SGR 48;2
    background code; transcript user rows carry their own different background,
    so the exact-code run keeps the locator off them. The prompt row is the
    bottom-most backgrounded row whose plain text starts with → after leading
    whitespace - the pane header's ❯ carries no background and never matches.
    Box content beyond the prompt glyph that renders plain (not dim, not
    reverse, not whitespace) is unsubmitted typing - a human draft, or a
    queued or just-submitted line lingering in the box before it migrates to
    the follow-ups panel; cursor renders its empty-composer suggestions dim
    with a reverse-video cursor letter, the same dim/plain fact claude
    renders. Every row of the box is scanned - a wrapped draft grows it."""
    lines = screen.replace("\r\n", "\n").split("\n")
    bg: dict[int, str] = {}
    for i, line in enumerate(lines):
        if (m := TRUECOLOR_BG.search(line)):
            bg[i] = m.group(1)
    prompt_idx = None
    for i in sorted(bg, reverse=True):
        if ANSI_CSI.sub("", lines[i]).strip().startswith(CURSOR_PROMPT_GLYPH):
            prompt_idx = i
            break
    if prompt_idx is None:
        return None
    code = bg[prompt_idx]
    lo = prompt_idx
    while lo - 1 in bg and bg[lo - 1] == code:
        lo -= 1
    hi = prompt_idx
    while hi + 1 in bg and bg[hi + 1] == code:
        hi += 1
    for i in range(lo, hi + 1):
        text, dims, revs = row_text_and_dim(lines[i])
        if i == prompt_idx:
            glyph_at = text.find(CURSOR_PROMPT_GLYPH)
            if glyph_at < 0:
                continue
            text, dims, revs = text[glyph_at + 1:], dims[glyph_at + 1:], revs[glyph_at + 1:]
        if any(ch.strip() and not dim and not rev for ch, dim, rev in zip(text, dims, revs)):
            return "typing"
    return "empty"


# claude's pane status chrome - never a consumer row, whatever it mutates into
# between the pre-send read and the poll. The spinner's frame set mutates per
# session and per CLI version (the round-2 hooks-phase capture emits a frame no
# captured list holds), so the family keys on its structural signature, never
# a glyph enumeration: a status row led by a symbol glyph and carrying the
# parenthesised activity marker with its elapsed-seconds component, whatever
# the glyph frame
STATUS_ROW_SHAPE = re.compile(r"^[^\x00-\x7f\w\s].*\(.*\d+s\b")
# the bottom status footer's row markers and the composer's queued-message hints
FOOTER_MARKERS = ("Model:", "⎇", "⏵⏵")
QUEUED_HINTS = ("ctrl+enter to send now", "Press up to edit queued messages")


def is_pane_chrome(row: str) -> bool:
    """The pane's own status chrome, never a consumer response. The busy pane's
    live bytes show three mutating families: the status spinner (a symbol-glyph
    row carrying the parenthesised activity marker with its elapsed-seconds
    component - it rewrites glyph, hook count and elapsed between two reads, so
    the pre-send exclusion never catches it), the composer's queued-message
    hints, and the bottom footer rows (context, cost and truncation all drift
    while a turn runs). Shape tests on the captured bytes, never a time
    heuristic."""
    if is_horizontal_rule(row):
        return True
    stripped = row.strip()
    if stripped.startswith(FOOTER_MARKERS):
        return True
    if any(hint in stripped for hint in QUEUED_HINTS):
        return True
    return STATUS_ROW_SHAPE.match(stripped) is not None


# cursor-agent pane chrome - the follow-ups panel (borders and │ rows) that
# carries a queued line's words, the braille spinner row with its Running/
# Working label, tip rows, the task-count row, the model/status footer (its
# pct drifts while a turn runs), and the box rows themselves (the → prefix)
CURSOR_PANEL_BORDER = re.compile(r"^\s*[┌└]─")
CURSOR_SPINNER = re.compile(r"^[⠀-⣿]+\s*(?:Running|Working)\b")
CURSOR_TASK_ROW = re.compile(r"^\s*\d+\s+tasks?\b")
CURSOR_FOOTER_PCT = re.compile(r"· \d+(?:\.\d+)?")
CURSOR_TIP = "Tip:"


def is_cursor_pane_chrome(row: str) -> bool:
    """The cursor pane's own status chrome, never a consumer response - the
    same job is_pane_chrome does for claude, on cursor's captured shapes: the
    follow-ups panel rows would otherwise read as a fresh consumer row
    carrying the queued line's words (the false-delivered face)."""
    if is_horizontal_rule(row):
        return True
    stripped = row.strip()
    if stripped.startswith(("│", CURSOR_PROMPT_GLYPH, CURSOR_TIP)):
        return True
    if CURSOR_PANEL_BORDER.match(stripped) or CURSOR_SPINNER.match(stripped) or CURSOR_TASK_ROW.match(stripped):
        return True
    return CURSOR_FOOTER_PCT.search(stripped) is not None


# The cwd row is deliberately not a shape: it is stable pane text, so the
# readback's pre-rows membership check covers it (a `startswith("/")` shape
# would eat a consumer reply that begins with a path).


@dataclass(slots=True, frozen=True)
class SeatGuard:
    """The per-harness pair behind the ring guard: how to read that harness's
    composer, and which rows of its pane are chrome for the readback. Adding
    a harness = one entry here plus its fixtures - no guarded-path edits."""

    box_state: Callable[[str], str | None]
    pane_chrome: Callable[[str], bool]


SEAT_GUARDS: dict[str, SeatGuard] = {
    "claude": SeatGuard(claude_prompt_box_state, is_pane_chrome),
    "cursor": SeatGuard(cursor_prompt_box_state, is_cursor_pane_chrome),
}


def prompt_box_state(screen: str, harness: str) -> str | None:
    """The seat's composer via its harness's registered detector: "empty",
    "typing", or None when the box cannot be seen. An unregistered harness is
    never read - ring_seat routes unprobed seats around this dispatcher, so a
    KeyError here is a wiring bug, not a fallback."""
    return SEAT_GUARDS[harness].box_state(screen)


def readback_classify(
    sent: str, pre: str, post: str, chrome: Callable[[str], bool] = is_pane_chrome
) -> tuple[str, str]:
    """The R140 classifier at ring scale (bin/lab-control.sh its landed
    readback_classify): delivered only when a row after the sent line's last
    trace is fresh against the pre-send read, queued when the line sits with
    nothing fresh after it, absent when no trace of the line survives."""
    def trimmed(row: str) -> str:
        # pane text carries ESC rendered as `^[` and CR at line ends
        return row.replace("^[", "").replace("\r", "").strip(" \t%")

    # a multiline submission renders as several pane rows; the last row of the
    # sent text is the freshest trace Enter lands after
    sent = trimmed(sent.splitlines()[-1]) if sent.splitlines() else ""
    pre_rows = [trimmed(row) for row in pre.splitlines()]
    post_rows = [trimmed(row) for row in post.splitlines()]
    pane_state = " ".join(post_rows[-3:]).strip()
    hit = next((i for i, row in reversed(list(enumerate(post_rows))) if sent and sent in row), None)
    # a pane row-wraps a long line across adjacent rows (the founding payload's
    # own done: path shape), so at the missed single-row match join adjacent
    # pairs - the R140 wrap mitigation verbatim; the raw rows keep the wrap
    # point's own spacing, which trimming would eat
    if hit is None:
        raw = [row.replace("\r", "") for row in post.splitlines()]
        hit = next((i + 1 for i in range(len(raw) - 1) if sent and sent in raw[i] + raw[i + 1]), None)
        # claude's wrapped rendering indents the continuation row at the seam
        # (the live bytes' two-space indent), so the raw join carries the indent
        # where the sent text has none - re-run the join with the seam stripped
        if hit is None:
            hit = next(
                (i + 1 for i in range(len(raw) - 1) if sent and sent in raw[i] + raw[i + 1].lstrip()),
                None,
            )
        if hit is None:
            # the founding payload wraps past two rows (a 230-char line holds
            # eight at a 57-column pane), and its word-boundary seams defeat
            # the pair joins too - the indent doubles the seam space the sent
            # text carries, and stripping it drops the space outright. Join
            # the whole post read with all whitespace squashed out of both
            # sides and map the match back to the row its last byte lands in:
            # that row is the freshest trace Enter lands after
            squashed = [re.sub(r"\s+", "", row) for row in raw]
            target = re.sub(r"\s+", "", sent)
            joined = "".join(squashed)
            start = joined.find(target) if target else -1
            if start >= 0:
                end = start + len(target) - 1
                spent = 0
                hit = next(
                    (i for i, row in enumerate(squashed) if (spent := spent + len(row)) > end),
                    None,
                )
    if hit is None:
        return "absent", f"absent; pane: {pane_state}"
    for row in post_rows[hit + 1:]:
        # a row the pre-send read already held is pane chrome, not a consumer
        # response - and so is a row of the pane's own status chrome, whatever
        # it mutated into - the two discriminators the false-delivered face
        # turns on
        if row and row != "❯" and row not in pre_rows and not chrome(row):
            return "delivered", f"delivered; fresh row: {row}"
    return "queued", f"queued-unverified; pane: {pane_state}"


def ring_readback(
    pane: str, line: str, pre_read: str, chrome: Callable[[str], bool] = is_pane_chrome
) -> tuple[RingOutcome, str]:
    """The post-send readback: pane reads polled 0.5 s apart to the 5 s cap,
    the sent line classified against the pre-send read - a vanished line
    names itself here, never at the next digest beat."""
    verdict, evidence = "absent", ""
    for poll in range(RING_READBACK_POLLS):
        try:
            post = herdr("pane", "read", "--source", "visible", pane)
        except HerdrError:
            post = ""
        verdict, evidence = readback_classify(line, pre_read, post, chrome=chrome)
        if verdict == "delivered":
            break
        if poll + 1 < RING_READBACK_POLLS:
            time.sleep(0.5)
    return {
        "delivered": (RingOutcome.RUNG, evidence),
        "queued": (RingOutcome.QUEUED, evidence),
    }.get(verdict, (RingOutcome.ABSENT, evidence))


def ring_seat(pane: str, line: str, wait_ms: int = RING_WAIT_MS) -> tuple[RingOutcome, str]:
    # the seat-level ring every line to a pane must go through: raw
    # `herdr agent prompt` types blind, splicing into a draft a human is
    # mid-typing, and Enter submits both (#70). The second return value is the
    # readback evidence, empty for every not-submitted deferral. The readback
    # runs for registered harnesses through their chrome predicate; an
    # unprobed send reports today's bare rung, no claim.
    harness = recipient_harness(pane)
    guard = SEAT_GUARDS.get(harness)
    try:
        herdr("agent", "wait", pane, "--until", "idle", "--until", "done", "--timeout", str(wait_ms))
    except HerdrError as exc:
        if exc.code == "timeout":
            # a busy recipient may not end its turn for hours (an orchestrator
            # waiting on subagents), and its turn-end inbox check is not
            # reliable (#37); a guarded harness takes a mid-turn prompt fine
            # once its composer is seen empty - the line queues in its input -
            # and herdr still refuses to prompt a blocked agent; an unprobed
            # harness is left alone (its fallback, unchanged)
            if guard is None:
                return RingOutcome.NOT_IDLE, ""
        elif exc.code in UNRUNG:
            return UNRUNG[exc.code], ""
        else:
            raise
    if guard is not None:
        # a draft in a guarded pane's composer means a human is mid-typing,
        # idle or mid-turn alike: prompting splices into the draft and Enter
        # submits both (#70's busy arm - the human types while the agent
        # works). Read the composer through the styled visible view - herdr's
        # detection view strips the rendering attributes that tell a
        # suggestion from a human's typed draft (claude renders its own
        # empty-composer suggestions dim while a human's typed draft renders
        # plain - cursor renders the same dim/plain fact - so the dim flag is
        # what tells a suggestion from typed text, the founding lost-ring
        # shape) - and defer the ring on anything but a provably empty box;
        # the mail stays in the inbox and the turn-end guard or a poke
        # surfaces it.
        try:
            screen = herdr("pane", "read", "--source", "visible", "--format", "ansi", pane)
        except HerdrError:
            return RingOutcome.COMPOSER_UNSEEN, ""
        state = prompt_box_state(screen, harness)
        if state == "typing":
            return RingOutcome.TYPING, ""
        if state is None:
            return RingOutcome.COMPOSER_UNSEEN, ""
    guarded = guard is not None
    # the pre-send read the readback diffs against, from the visible source in
    # plain text: the readback matches on words, not rendering attributes
    pre_read = ""
    if guarded:
        try:
            pre_read = herdr("pane", "read", "--source", "visible", pane)
        except HerdrError:
            # no pre-send read, no honest classification - refuse rather than
            # promise a delivery nothing verified
            return RingOutcome.COMPOSER_UNSEEN, ""
    try:
        herdr("agent", "prompt", pane, line)
    except HerdrError as exc:
        if exc.code in UNRUNG:
            return UNRUNG[exc.code], ""
        raise
    if not guarded:
        return RingOutcome.RUNG, ""
    return ring_readback(pane, line, pre_read, chrome=guard.pane_chrome)


def ring(root: Path, name: str) -> tuple[RingOutcome, str]:
    # the herdr name is not the member's identity (one pane, several meshes,
    # several names): ring the member's seat pane, and only while its recorded
    # claim is live - never a bare name
    member = member_named(root, name)
    if member is None or not live_claim(member)[0]:
        return RingOutcome.OFFLINE, ""
    return ring_seat(member.seat.pane, wake_line(root, name), wait_ms=MAIL_RING_WAIT_MS)


def ring_all(root: Path, paths: dict[str, Path]) -> None:
    failed = False
    for name, path in paths.items():
        try:
            outcome, evidence = ring(root, name)
        except HerdrError as exc:
            typer.echo(f"{path} written, ring failed: {exc}")
            failed = True
            continue
        # the evidence line precedes the outcome so the outcome stays the
        # line a caller greps for
        if evidence:
            typer.echo(f"readback: {evidence}")
        typer.echo(f"{path} {outcome}")
    if failed:
        raise typer.Exit(1)


def report_unrung(paths: dict[str, Path]) -> None:
    for path in paths.values():
        typer.echo(f"{path} written, not rung (--no-ring)")


def deliver(root: Path, sender: str, msg_id: str, kind: Kind, recipients: list[str], ring_now: bool) -> None:
    paths = write_messages(root, sender, msg_id, kind, read_body(), recipients)
    member = member_named(root, sender)
    log_event(root, event="sent", sender=sender, session=member.harness_session if member else None,
              id=msg_id, kind=str(kind), to=recipients)
    if ring_now:
        ring_all(root, paths)
    else:
        report_unrung(paths)


def log_closed(root: Path, closer: str, request_sender: str, msg_id: str) -> None:
    """Append one `closed` event - the recipient's word that no reply is coming."""
    member = member_named(root, closer)
    log_event(root, event="closed", member=closer,
              session=member.harness_session if member else None,
              id=msg_id, to=[request_sender])


def autoclose_referenced(root: Path, sender: str, slug: str) -> None:
    """A `re-<seq>-` slug reports against a pending request addressed to the
    sender; retire that request when the seq names exactly one.

    Integer match on the seq, the same match `reply` performs - never a
    string prefix on the id, so a zero-padded id never over-matches a longer
    future seq and an unpadded slug still hits. Ambiguous or no match never
    fails the send: several print a note (the explicit verb disambiguates),
    none stay silent - a `re-` slug may reference a reply or an old id."""
    match = re.fullmatch(r"re-(\d+)(?:-.*)?", slug)
    if match is None:
        return
    seq = int(match.group(1))
    mine = [(request_sender, request)
            for request_sender, requests in pending_by_member(root).items()
            for request in requests
            if sender in request.to and int(request.msg_id.split("-", 1)[0]) == seq]
    if len(mine) == 1:
        request_sender, request = mine[0]
        log_closed(root, sender, request_sender, request.msg_id)
        typer.echo(f"closed {request.msg_id} from {request_sender} (referenced by {slug})")
    elif len(mine) > 1:
        names = ", ".join(f"{request.msg_id} (from {request_sender})" for request_sender, request in mine)
        typer.echo(f"note: seq {seq} matches several pending requests: {names} - no auto-close, use close <id> <from>")


@app.command()
def send(slug: str, to: list[str], ring_now: RingFlag = True) -> None:
    """Send a new request (body on stdin) to one or more members."""
    if not ring_now:
        fail("--no-ring is not available on send - a request needs its recipient rung "
             "(a 2026-10 strand sat unread for hours behind --no-ring); "
             "use --no-ring only on replies and FYI mail")
    root = mailbox_root()
    check_token(slug, "slug")
    check_members(root, to)
    sender = own_name(root)
    seq = f"{next_seq(root, sender):0{SEQ_WIDTH}d}"
    # agents often prefix the slug with the seq they expect; the helper adds it
    msg_id = f"{seq}-{slug.removeprefix(f'{seq}-')}"
    deliver(root, sender, msg_id, Kind.MSG, to, ring_now)
    autoclose_referenced(root, sender, slug)


def resolve_request(root: Path, me: str, ref: str, sender: str) -> Message:
    """The request REF from SENDER, unread, in flight or handled, in ME's inbox."""
    match = REQUEST_REF_RE.fullmatch(Path(ref).name)
    if match is None:
        fail(f"id {ref!r} must be the request's seq (7), id (007-review-api) or filename")
    seq, slug = int(match["seq"]), match["slug"]
    box = root / "inboxes" / me
    # requests only: a `.reply` carries the replier's name with *your* seq, so it can share <sender, seq> with one
    # inflight sits between unread and handled: a request taken but not yet acked must still resolve
    requests = [m for d in (box, box / "inflight", box / "handled") for m in messages_in(d) if m.kind is Kind.MSG]
    same_seq = [m for m in requests if m.seq == seq]
    found = [m for m in same_seq if m.sender == sender and slug in (None, m.slug)]
    if len(found) == 1:
        return found[0]
    if found:
        fail(f"id {ref!r} matches several requests from {sender!r}: {[m.path.name for m in found]}")
    if same_seq:
        listing = ", ".join(f"{m.path.name} (from {m.sender})" for m in same_seq)
        fail(f"no request {ref!r} from {sender!r}; requests with seq {seq}: {listing} - reply to the name before the first '.'\n{FOLLOW_UP_SEND}")
    from_sender = [m.msg_id for m in requests if m.sender == sender]
    fail(f"no request with seq {seq} in your inbox, inflight/ or handled/; requests from {sender!r}: {from_sender or 'none'}\n{FOLLOW_UP_SEND}")


@app.command()
def reply(
    ref: Annotated[str, typer.Argument(metavar="ID", help="The request's seq (7), id (007-review-api) or filename")],
    to: str,
    ring_now: RingFlag = True,
) -> None:
    """Reply (body on stdin) to request ID from member TO."""
    root = mailbox_root()
    check_members(root, [to])
    sender = own_name(root)
    if to == sender:
        fail(f"you are {sender!r}; address the reply to the request's sender - the name before the first '.' in its filename\n{FOLLOW_UP_SEND}")
    request = resolve_request(root, sender, ref, to)
    deliver(root, sender, request.msg_id, Kind.REPLY, [to], ring_now)


@app.command()
def close(
    ref: Annotated[str, typer.Argument(metavar="ID", help="The request's seq (7), id (007-review-api) or filename")],
    to: str,
) -> None:
    """Mark request ID from member TO answered with no reply coming - no mail written, no ring."""
    root = mailbox_root()
    check_members(root, [to])
    sender = own_name(root)
    if to == sender:
        fail(f"you are {sender!r}; close marks a request another member sent you - the name before the first '.' in its filename")
    request = resolve_request(root, sender, ref, to)
    outstanding = [p for p in pending_by_member(root).get(to, []) if p.msg_id == request.msg_id]
    if not outstanding:
        typer.echo(f"{request.msg_id} from {to} is already answered - nothing to close")
        return
    log_closed(root, sender, to, request.msg_id)
    typer.echo(f"closed {request.msg_id} from {to}")


@app.command()
def inbox() -> None:
    """List your unread mail without taking it."""
    root = mailbox_root()
    unread = messages_in(root / "inboxes" / own_name(root))
    if not unread:
        typer.echo(NO_MAIL)
    for message in unread:
        try:
            typer.echo(describe(message))
        except FileNotFoundError:
            continue  # a concurrent take already moved it to inflight
    nag = heartbeat_not_running_line(root)
    if nag:
        typer.echo(nag)


@app.command()
def take(full: Annotated[bool, typer.Option("--full", help="Re-print unacked inflight bodies; the default prints one header line each")] = False) -> None:
    """Print all unread mail, moving exactly what was printed to inflight/.

    Unacked inflight mail from an earlier turn prints as one header line -
    its filename, size and the --full pointer, no body - so an outstanding
    message stays visible without re-ingesting it on every take; --full
    re-prints those bodies. Presentation, not the ack: `ack` confirms, and a
    turn that dies between take and ack loses nothing - the mail stays in
    inflight/, its header names the file, and the next take replays it."""
    root = mailbox_root()
    name = verified_own_name(root)
    box = root / "inboxes" / name
    printed: list[Message] = []
    for message in messages_in(box / "inflight"):
        try:
            if full:
                typer.echo(f"=== {message.path.name} (unacked - printed before)")
                typer.echo(message.path.read_text().rstrip("\n"))
            else:
                size = message.path.stat().st_size
                typer.echo(f"=== {message.path.name} (unacked - printed before; {size} B; take --full for the body)")
        except FileNotFoundError:
            continue  # a concurrent ack promoted it
        printed.append(message)
    for message in messages_in(box):
        try:
            body = message.path.read_text()
        except FileNotFoundError:
            continue  # a concurrent take already presented it
        typer.echo(f"=== {message.path.name}")
        typer.echo(body.rstrip("\n"))
        printed.append(message)
    if not printed:
        typer.echo(NO_MAIL)
        nag = heartbeat_not_running_line(root)
        if nag:
            typer.echo(nag)
        return
    (box / "inflight").mkdir(parents=True, exist_ok=True)  # an old-mesh member may lack it
    for message in printed:
        # a no-op rename for a re-printed inflight file (same path), and a
        # suppressed FileNotFoundError for one a concurrent take or ack moved
        with contextlib.suppress(FileNotFoundError):
            message.path.rename(box / "inflight" / message.path.name)
    member = member_named(root, name)
    log_event(root, event="taken", member=name, session=member.harness_session if member else None,
              files=[message.path.name for message in printed])
    nag = heartbeat_not_running_line(root)
    if nag:
        typer.echo(nag)


@app.command()
def ack() -> None:
    """Confirm everything taken: promote inflight mail to handled/ - that move is the ack the sender sees."""
    root = mailbox_root()
    name = verified_own_name(root)
    box = root / "inboxes" / name
    unacked = messages_in(box / "inflight")
    if not unacked:
        typer.echo(NO_UNACKED)
        return
    (box / "handled").mkdir(parents=True, exist_ok=True)
    promoted: list[str] = []
    for message in unacked:
        with contextlib.suppress(FileNotFoundError):  # a concurrent ack promoted it
            message.path.rename(box / "handled" / message.path.name)
            promoted.append(message.path.name)
    if promoted:
        member = member_named(root, name)
        log_event(root, event="acked", member=name, session=member.harness_session if member else None,
                  files=promoted)


@app.command()
def status(member: Annotated[str | None, typer.Argument(help="Show only this member's unread ids and pending requests")] = None) -> None:
    """Every member's role and unread/inflight/handled/pending counts, or one member's unread ids and pending requests. Needs no join."""
    root = mailbox_root()
    pending = pending_by_member(root)
    if member is not None:
        check_members(root, [member])
        unread = messages_in(root / "inboxes" / member, strict=False)
        if not unread:
            typer.echo(f"{member}: {NO_MAIL}")
        for message in unread:
            typer.echo(describe(message))
        for request in pending.get(member, []):
            typer.echo(f"pending  {request.msg_id}  to {', '.join(request.to)}")
        nag = heartbeat_not_running_line(root)
        if nag:
            typer.echo(nag)
        return
    for m in members(root):
        box = root / "inboxes" / m.name
        # lenient: one member's stray file must not hide every member's counts
        typer.echo(
            f"{m.name}  ({m.role})  unread {len(messages_in(box, strict=False))}  "
            f"inflight {len(messages_in(box / 'inflight', strict=False))}  "
            f"handled {len(messages_in(box / 'handled', strict=False))}  "
            f"pending {len(pending.get(m.name, []))}"
        )
    nag = heartbeat_not_running_line(root)
    if nag:
        typer.echo(nag)


@app.command()
def poke(member: str) -> None:
    """Ring MEMBER again about mail already waiting in its inbox."""
    root = mailbox_root()
    check_members(root, [member])
    own_name(root)  # poking is acting in the mesh, so only members may
    if not messages_in(root / "inboxes" / member, strict=False):
        # a wake line with nothing behind it trains members to ignore wake lines
        typer.echo(f"{member}: nothing to poke")
        return
    try:
        outcome, evidence = ring(root, member)
    except HerdrError as exc:
        fail(f"{member}: ring failed: {exc}")
    if evidence:
        typer.echo(f"readback: {evidence}")
    typer.echo(f"{member}: {outcome}")


# the ring verb writes no mail, so the deferral outcomes' "waits in its
# inbox" remedy is false for it - its deferrals get their own wording
SEAT_DEFERRED = {
    RingOutcome.TYPING: "not rung: unsubmitted typing sits in the seat's composer - the line was not submitted; resend it once the composer is clear",
    RingOutcome.COMPOSER_UNSEEN: (
        "not rung: the seat's composer could not be seen (menu, overlay, or herdr without"
        " `pane read --source visible`) - the line was not submitted; resend when the view is clear"
    ),
    RingOutcome.BLOCKED: "not rung: the seat is at a permission prompt - the line was not submitted; resend once it is unblocked",
    RingOutcome.NOT_IDLE: "not rung: the seat stayed busy and mid-turn prompting is unverified for its harness - the line was not submitted; resend later",
    RingOutcome.ABSENT: "not rung: the sent line left no trace in the seat's pane - it was not submitted; resend it",
}


@app.command("ring")
def ring_any(
    target: Annotated[str, typer.Argument(help="Pane id, herdr agent name, or mesh member name of any live seat")],
    line: Annotated[str, typer.Argument(help="The line to submit; deferred while a draft sits in the seat's composer")],
    wait_ms: Annotated[int, typer.Option("--wait-ms", help="Idle wait before the mid-turn fallback; 0 = check and fall through at once")] = RING_WAIT_MS,
) -> None:
    """Submit LINE to any agent seat with the composer guard. Needs no join; writes no mail. Exit 3 when not submitted."""
    record = agent_record_for_pane(target)
    resolution = ""
    if not record:
        # a name herdr does not know can still name a live seat: the mesh
        # member record resolves it to its recorded pane (row G871's founding
        # shape - the pane's agent holds another herdr name or none, so the
        # name lookup misses while the seat lives). The record's pane id is
        # the anchor; the bare skill checkout holds no records, so a member
        # name still refuses there, the route named.
        root = mesh_root_if_any()
        member = member_named(root, target) if root is not None else None
        if member is not None and member.seat is not None:
            record = agent_record_for_pane(member.seat.pane)
            if record:
                resolution = (
                    f"resolution: {target} names no live herdr agent; the member "
                    f"record's pane {member.seat.pane} is live - ringing it"
                )
            else:
                fail(
                    f"{target}: no live herdr agent at that seat; the member record names "
                    f"pane {member.seat.pane}, which holds no live agent"
                )
        else:
            fail(
                f"{target}: no live herdr agent at that seat; when it names a mesh member, "
                "run this as that mesh's bin/mailbox or ring the member's pane id"
            )
    pane = record["pane_id"]
    try:
        outcome, evidence = ring_seat(pane, line, wait_ms)
    except HerdrError as exc:
        fail(f"{target}: ring failed: {exc}")
    if resolution:
        typer.echo(resolution)
    if evidence:
        typer.echo(f"readback: {evidence}")
    typer.echo(f"{pane}: {SEAT_DEFERRED.get(outcome, outcome)}")
    if outcome in SEAT_DEFERRED:
        typer.echo("mailbox ring writes no mail - nothing waits anywhere; the caller resends")
        raise typer.Exit(3)


# --- member control: launchers, spawn, restart, inspect, interrupt, retire, adopt ---
#
# A mesh's members are started, repaired and stopped through launchers the user
# approved in <mesh>/launchers.toml, and every control verb resolves its target
# through a member record - never a free pane id, so a verb cannot reach a pane
# outside its mesh.

SPAWN_READY_TIMEOUT_S = 120.0
SPAWN_POLL_S = 1.0
SHELL_RETURN_TIMEOUT_S = 30.0
SHELL_POLL_S = 0.5
SIGTERM_GRACE_S = 10.0
FRESH_TRANSCRIPT_S = 10 * 60  # a live turn younger than this is never killed without --force
ESCAPE_IDLE_WAIT_MS = 30_000
START_LOCK_WAIT_S = 30.0

# herdr reports an agent's own session id under the harness's projects dir; the
# member file records no cwd, so the transcript is found by session id alone
CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"


@dataclass(frozen=True, slots=True)
class Launcher:
    """One approved way to start an agent in this mesh: a launchers.toml entry.

    `command` is an argv list, never a shell line, so it renders both into the
    line `pane run` types and into herdr's per-pane restore argv. `resume` holds
    the argv suffix that resumes a session, with `{session}` filled from the
    member record at restore time."""

    command: tuple[str, ...]
    harness: str  # a herdr agent kind (claude, codex, pi, ...), checked against what herdr detects
    env: dict[str, str] = field(default_factory=dict)
    resume: tuple[str, ...] | None = None
    billed: bool = False


# a plain command name (no slash, no shell metacharacter); an absolute path is
# the one other allowed first element - a shell line is never either
COMMAND_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+@-]*$")
LAUNCHER_KEYS = ("command", "env", "harness", "resume", "billed")
# herdr rejects a restore argv whose elements carry apostrophes or control
# characters, so a launcher that cannot be registered as-is is refused at parse
UNREGISTERABLE = re.compile(r"['\x00-\x1f\x7f]")


def parse_launchers(text: str, path: Path) -> tuple[dict[str, Launcher], list[str]]:
    """(launchers by id, problems); the loader fails loudly on any problem."""
    problems: list[str] = []
    launchers: dict[str, Launcher] = {}
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return {}, [f"{path} is not valid TOML: {exc}"]
    for key, entry in doc.items():
        if not NAME_RE.fullmatch(key):
            problems.append(f"{path}: launcher id {key!r} must be lowercase letters, digits and single hyphens")
            continue
        if not isinstance(entry, dict):
            problems.append(f"{path}: [{key}] must be a table holding command, harness, ...")
            continue
        where = f"{path}: [{key}]"
        unknown = sorted(set(entry) - set(LAUNCHER_KEYS))
        if unknown:
            problems.append(f"{where} has unknown keys {unknown}; allowed: {sorted(LAUNCHER_KEYS)}")
        command = entry.get("command")
        bad = bool(unknown)
        if not (isinstance(command, list) and command and all(isinstance(el, str) and el for el in command)):
            problems.append(f"{where} command must be a non-empty list of strings - an argv list, never a shell line")
            bad = True
        else:
            first = command[0]
            if not (COMMAND_NAME_RE.fullmatch(first) or (first.startswith("/") and not any(c.isspace() for c in first))):
                problems.append(f"{where} command's first element {first!r} must be a plain command name or an absolute path")
                bad = True
            if any(ch in "".join(command) for ch in ";|&$`\\"):
                problems.append(f"{where} command carries shell metacharacters - it must be an argv list, never a shell line")
                bad = True
            if UNREGISTERABLE.search("".join(command)):
                problems.append(f"{where} command carries an apostrophe or control character - herdr refuses it as a restore argv")
                bad = True
        harness = entry.get("harness")
        if not (isinstance(harness, str) and harness):
            problems.append(f"{where} harness must be a herdr agent kind (e.g. claude), a non-empty string")
            bad = True
        resume = entry.get("resume")
        if resume is not None:
            if not (isinstance(resume, list) and resume and all(isinstance(el, str) and el for el in resume)):
                problems.append(f"{where} resume must be a non-empty list of strings, e.g. [\"--resume\", \"{{session}}\"]")
                bad = True
            elif not any("{session}" in el for el in resume):
                problems.append(f"{where} resume must contain the {{session}} placeholder")
                bad = True
            elif UNREGISTERABLE.search("".join(resume)):
                problems.append(f"{where} resume carries an apostrophe or control character - herdr refuses it as a restore argv")
                bad = True
        env = entry.get("env")
        if env is None:
            env = {}
        elif not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            problems.append(f"{where} env must be a table of string to string")
            bad = True
        elif UNREGISTERABLE.search("".join(env.values())):
            problems.append(f"{where} env values carry an apostrophe or control character - herdr refuses them as a restore argv")
            bad = True
        billed = entry.get("billed", False)
        if not isinstance(billed, bool):
            problems.append(f"{where} billed must be true or false")
            bad = True
        if bad:
            continue
        launchers[key] = Launcher(
            command=tuple(command),
            harness=harness,
            env=dict(env),
            resume=tuple(resume) if resume is not None else None,
            billed=billed,
        )
    return launchers, problems


def load_launchers(root: Path, *, required: bool) -> dict[str, Launcher]:
    """The mesh's launcher allowlist; empty when absent and not required, never a guess."""
    path = root / "launchers.toml"
    if not path.is_file():
        if required:
            fail(
                f"{path} is missing - it is the allowlist of commands that may start an agent in"
                " this mesh; the user writes it (an agent may only propose content for the user"
                " to approve in chat), then spawn and restart work"
            )
        return {}
    launchers, problems = parse_launchers(path.read_text(), path)
    if problems:
        fail("; ".join(problems))
    return launchers


def resume_argv_for(launcher: Launcher, session: str) -> tuple[str, ...]:
    """The launcher as herdr's per-pane restore argv: `env K=V ... <command...> <resume...>`.

    herdr's restore re-runs this after a server restart, so the member comes back
    through its launcher with its environment instead of the bare harness - the
    observed container-restart failure. `env` is the plain first command because
    herdr requires one."""
    env_args = [f"{key}={value}" for key, value in launcher.env.items()]
    resume_args = [el.replace("{session}", session) for el in (launcher.resume or ())]
    return ("env", *env_args, *launcher.command, *resume_args)


def launch_shell_line(launcher: Launcher, extra: tuple[str, ...] = ()) -> str:
    """The launcher as one shell line for `herdr pane run` - the same argv the restore
    registration records, so a restart relaunches exactly what a restore would."""
    env_args = [f"{key}={value}" for key, value in launcher.env.items()]
    return shlex.join(["env", *env_args, *launcher.command, *extra])


# the source id herdr sees for the mailbox's own agent-state reports; `herdr:` is
# reserved for herdr's own integrations and must never be used
MAILBOX_SOURCE = "mailbox"


def register_restore(pane: str, launcher: Launcher, session: str) -> None:
    """Register the launcher as the pane's herdr resume command, so herdr's own session
    restore relaunches the member through it (with its environment) after a restart."""
    herdr(
        "pane", "report-agent-session", pane,
        "--source", MAILBOX_SOURCE, "--agent", launcher.harness,
        "--agent-session-id", session,
        "--", *resume_argv_for(launcher, session),
    )


def transcript_last_write(session: str) -> float | None:
    """The newest modification time across the session's transcript and its subagents'
    transcripts, or None when no transcript is on disk."""
    if not session:
        return None
    times = [
        path.stat().st_mtime
        for pattern in (f"*/{session}.jsonl", f"*/{session}/subagents/*.jsonl")
        for path in CLAUDE_PROJECTS.glob(pattern)
        if path.is_file()
    ]
    return max(times, default=None)


def member_or_fail(root: Path, name: str) -> Member:
    member = member_named(root, name)
    if member is None:
        fail(f"not a mesh member: {name}; members are {sorted(m.name for m in members(root))}")
    return member


def own_workspace() -> str:
    workspace = os.environ.get("HERDR_WORKSPACE_ID")
    if not workspace:
        fail("HERDR_WORKSPACE_ID is unset; run this from an agent session inside a herdr pane")
    return workspace


def wait_until_agent_ready(
    pane: str, harness: str, timeout_s: float, poll_s: float, what: str
) -> dict[str, Any]:
    """Poll `herdr agent get` until the pane's agent is detected as HARNESS and idle.

    `herdr agent start` is never used - it runs the harness's canonical executable
    instead of the launcher, so the launcher (and the spend it pins) is bypassed."""
    deadline = time.monotonic() + timeout_s
    while True:
        record = agent_record_for_pane(pane)
        if record:
            detected = record.get("agent")
            if detected != harness:
                fail(
                    f"{what}: herdr detected {detected!r} in pane {pane}, but the launcher"
                    f" declares harness {harness!r} - a harness mismatch; the tab is left open"
                )
            if record.get("agent_status") == "idle":
                return record
        if time.monotonic() >= deadline:
            state = (
                f"agent {record.get('agent')!r}, status {record.get('agent_status')!r}"
                if record else "no agent detected"
            )
            fail(f"{what}: pane {pane} not ready within {timeout_s:g}s ({state}); the tab is left open for inspection")
        time.sleep(poll_s)


def wait_for_member_record(root: Path, name: str, pane: str, timeout_s: float, poll_s: float, what: str) -> Member:
    """The member record once NAME claims PANE live - the join the spawned member runs."""
    deadline = time.monotonic() + timeout_s
    while True:
        member = member_named(root, name)
        if member is not None and member.seat is not None and member.seat.pane == pane and live_claim(member)[0]:
            return member
        if time.monotonic() >= deadline:
            fail(f"{what}: no live member record for {name} at pane {pane} within {timeout_s:g}s - the join never landed; the tab is left open for inspection")
        time.sleep(poll_s)


def join_line_for(
    root: Path, name: str, role: str, launcher: str, spawned_by: str, tab: str, intro: str | None
) -> str:
    line = (
        f"{root / 'bin' / 'mailbox'} join {name} --role {shlex.quote(role)} "
        f"--launcher {launcher} --spawned-by {spawned_by} --tab {tab}"
    )
    # the intro carries what the connect prompt used to - e.g. "Load the orchestrator skill"
    return f"{line}\n{intro}" if intro else line


def wait_for_shell(pane: str, timeout_s: float, poll_s: float = SHELL_POLL_S) -> bool:
    """True once the pane holds no herdr agent - its process ended and the shell is back."""
    deadline = time.monotonic() + timeout_s
    while True:
        if not agent_record_for_pane(pane):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_s)


def foreground_pid(pane: str) -> int:
    info = json.loads(herdr("pane", "process-info", "--pane", pane))["result"]["process_info"]
    processes = info.get("foreground_processes") or []
    pid = processes[0]["pid"] if processes else info.get("foreground_process_group_id")
    if not isinstance(pid, int):
        fail(f"pane {pane} reports no foreground pid to signal")
    return pid


# the harnesses with an exit recipe; restart and retire refuse a harness without one
EXIT_RECIPES = ("claude",)
# Escape safely interrupts a turn only on these harnesses
INTERRUPT_HARNESSES = ("claude",)


class InterruptUnconfirmed(Exception):
    """Escape was sent but the seat did not go idle within the bound."""


def interrupt_seat(member: Member, line: str | None, step: str) -> tuple[RingOutcome, str] | None:
    """Stop the member's turn: composer guard, Escape, a bounded idle wait, then submit
    LINE - the one mechanism behind the interrupt verb and the heartbeat's interrupt
    action. Returns the ring outcome when a line was given, None otherwise."""
    if member.seat is None:
        fail(f"{step}: {member.name} records no seat")
    pane = member.seat.pane
    record = agent_record_for_pane(pane)
    if not record:
        fail(f"{step}: no live agent at {member.name}'s seat (pane {pane})")
    harness = record.get("agent") or member.harness
    if harness not in INTERRUPT_HARNESSES:
        fail(
            f"{step}: Escape does not safely interrupt a {harness!r} turn - interrupt is"
            f" valid for {INTERRUPT_HARNESSES} members only"
        )
    guard = SEAT_GUARDS[harness]
    # the composer check runs before Escape so a human's draft is never cleared
    try:
        screen = herdr("pane", "read", "--source", "visible", "--format", "ansi", pane)
    except HerdrError:
        screen = ""
    if guard.box_state(screen) == "typing":
        fail(f"{step}: unsubmitted typing sits in {member.name}'s composer - a human may be mid-draft; retry once it clears")
    herdr("agent", "send-keys", pane, "esc")
    try:
        herdr("agent", "wait", pane, "--until", "idle", "--timeout", str(ESCAPE_IDLE_WAIT_MS))
    except HerdrError as exc:
        if exc.code == "timeout":
            raise InterruptUnconfirmed(
                f"{step}: {member.name}'s seat did not go idle within {ESCAPE_IDLE_WAIT_MS // 1000}s of Escape"
            ) from exc
        raise
    if line is None:
        return None
    return ring_seat(pane, line, wait_ms=MAIL_RING_WAIT_MS)


def exit_agent_in_place(member: Member, step: str) -> None:
    """Stop the member's live agent in its pane with the harness's exit recipe, leaving
    the pane at its shell. A pane that already sits at its shell is left alone."""
    if member.seat is None:
        fail(f"{step}: {member.name} records no seat")
    pane = member.seat.pane
    record = agent_record_for_pane(pane)
    if not record:
        return
    harness = record.get("agent") or member.harness
    if harness not in EXIT_RECIPES:
        fail(f"{step}: no exit recipe for harness {harness!r} - one is added when that harness is")
    guard = SEAT_GUARDS[harness]
    try:
        screen = herdr("pane", "read", "--source", "visible", "--format", "ansi", pane)
    except HerdrError:
        screen = ""
    if guard.box_state(screen) == "typing":
        fail(f"{step}: unsubmitted typing sits in {member.name}'s composer - a human may be mid-draft; retry once it clears")
    # claude's recipe: Escape (out of any running turn, composer guarded), then /exit
    # through the guarded ring
    herdr("agent", "send-keys", pane, "esc")
    outcome, _ = ring_seat(pane, "/exit", wait_ms=MAIL_RING_WAIT_MS)
    if outcome in (RingOutcome.TYPING, RingOutcome.COMPOSER_UNSEEN, RingOutcome.BLOCKED, RingOutcome.NOT_IDLE):
        fail(f"{step}: /exit could not be submitted to {member.name}'s pane ({SEAT_DEFERRED.get(outcome, outcome)})")
    # RUNG, QUEUED or ABSENT: an exiting agent scrolls its own echo away, so the
    # pane's return to its shell is the real confirmation the line landed
    if wait_for_shell(pane, SHELL_RETURN_TIMEOUT_S):
        return
    # the pid-scoped signal fallback: only the pane's own foreground process
    pid = foreground_pid(pane)
    os.kill(pid, signal.SIGTERM)
    if not wait_for_shell(pane, SIGTERM_GRACE_S):
        fail(f"{step}: pane {pane} still holds a foreground process after SIGTERM to pid {pid}")


def restart_member(
    root: Path, member: Member, caller: str, reason: str, *, force: bool,
    ready_timeout_s: float = SPAWN_READY_TIMEOUT_S,
) -> None:
    """Relaunch MEMBER's own session in its pane through its recorded launcher, resuming
    its conversation - the core the restart verb and the heartbeat's restart action share.

    CALLER names the acting identity (`heartbeat` for the loop, which is no member)."""
    step = f"restart {member.name}"
    launchers = load_launchers(root, required=True)
    if member.launcher is None:
        fail(f"{member.name} records no launcher; record one first: bin/mailbox adopt {member.name} --launcher <id>")
    launcher = launchers.get(member.launcher)
    if launcher is None:
        fail(f"launcher {member.launcher!r} is not in {root / 'launchers.toml'}; known: {sorted(launchers)}")
    if launcher.resume is None:
        fail(f"launcher {member.launcher!r} declares no resume arguments - {member.name}'s session cannot be resumed through it")
    if member.seat is None:
        fail(f"{step}: {member.name} records no seat")
    pane = member.seat.pane
    record = agent_record_for_pane(pane)
    if record and not force and record.get("agent_status") == "working" and member.harness == "claude" and member.harness_session:
        last_write = transcript_last_write(member.harness_session)
        if last_write is not None and time.time() - last_write < FRESH_TRANSCRIPT_S:
            age = time.time() - last_write
            fail(
                f"{member.name} is working and its transcript was written {age:.0f}s ago - a live"
                " turn; pass --force to restart it anyway"
            )
    if record:
        exit_agent_in_place(member, step)
    session = member.harness_session
    if not session:
        fail(f"{step}: {member.name} records no harness session to resume")
    herdr("pane", "run", pane, launch_shell_line(launcher, tuple(el.replace("{session}", session) for el in launcher.resume)))
    ready = wait_until_agent_ready(pane, launcher.harness, ready_timeout_s, SPAWN_POLL_S, step)
    live_session = (ready.get("agent_session") or {}).get("value")
    # the record is refreshed only from what herdr reports in the member's own seat -
    # another pane is never adopted
    if live_session and live_session != member.harness_session:
        write_member(root, replace(member, harness_session=live_session))
        typer.echo(f"harness session refreshed: {member.harness_session} -> {live_session}")
    session = live_session or member.harness_session
    register_restore(pane, launcher, session)
    typer.echo(f"restore registered: {' '.join(resume_argv_for(launcher, session))}")
    wake = (
        f"you were restarted by {caller}"
        + (f" ({reason})" if reason else "")
        + "; run take and continue your work - contract: ../../README.md"
    )
    outcome, evidence = ring_seat(pane, wake, wait_ms=MAIL_RING_WAIT_MS)
    if evidence:
        typer.echo(f"readback: {evidence}")
    typer.echo(f"{member.name}: {outcome}")
    log_event(root, event="restart", member=member.name, by=caller, reason=reason or None,
              pane=pane, launcher=member.launcher, session=session)


@app.command()
def spawn(
    name: Annotated[str, typer.Argument(help="The new member's name")],
    role: Annotated[str, typer.Option(help="The new member's role, free text")],
    launcher: Annotated[str, typer.Option(help="The launchers.toml id to start the member through")],
    cwd: Annotated[Path | None, typer.Option(help="Working directory for the new member's pane; default: the caller's")] = None,
    intro: Annotated[str | None, typer.Option(help="Line(s) submitted after the join command, e.g. 'Load the orchestrator skill'")] = None,
    ready_timeout_s: Annotated[float, typer.Option(help="Bound, in seconds, for herdr to detect the new agent ready")] = SPAWN_READY_TIMEOUT_S,
) -> None:
    """Start a new member in a new labelled herdr tab, through an approved launcher, joined to the mesh."""
    root = mailbox_root()
    caller = own_name(root)
    check_token(name, "name")
    if name in RESERVED_NAMES:
        fail(f"{name!r} is a reserved name - it can never be a member")
    existing = member_named(root, name)
    if existing is not None and existing.seat is not None and live_claim(existing)[0]:
        fail(f"name {name!r} is held by the live member in pane {existing.seat.pane}; pick another name")
    launchers = load_launchers(root, required=True)
    if launcher not in launchers:
        fail(f"launcher {launcher!r} is not in {root / 'launchers.toml'}; known: {sorted(launchers)}")
    conf = launchers[launcher]
    args = ["tab", "create", "--workspace", own_workspace(), "--label", name, "--no-focus"]
    if cwd is not None:
        args += ["--cwd", str(cwd)]
    created = json.loads(herdr(*args))["result"]
    tab_id = created["tab"]["tab_id"]
    pane = created["root_pane"]["pane_id"]
    try:
        herdr("pane", "rename", pane, name)
        herdr("pane", "run", pane, launch_shell_line(conf))
        record = wait_until_agent_ready(pane, conf.harness, ready_timeout_s, SPAWN_POLL_S, f"spawn {name}")
        session = (record.get("agent_session") or {}).get("value")
        outcome, evidence = ring_seat(
            pane, join_line_for(root, name, role, launcher, caller, tab_id, intro), wait_ms=MAIL_RING_WAIT_MS
        )
        if evidence:
            typer.echo(f"readback: {evidence}")
        if outcome not in (RingOutcome.RUNG, RingOutcome.QUEUED):
            fail(f"spawn {name}: the join line was not submitted ({SEAT_DEFERRED.get(outcome, outcome)})")
        joined = wait_for_member_record(root, name, pane, ready_timeout_s, SPAWN_POLL_S, f"spawn {name}")
        session = joined.harness_session or session
        if not session:
            fail(
                f"spawn {name}: herdr reports no harness session for the new member, so the"
                " launcher's resume arguments cannot be registered"
            )
        register_restore(pane, conf, session)
    except HerdrError as exc:
        typer.echo(f"mailbox: herdr failed during spawn: {exc}", err=True)
        typer.echo(f"mailbox: tab {tab_id} (pane {pane}) is left open for inspection - inspect it, then retire --force it or close it", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        typer.echo(f"mailbox: tab {tab_id} (pane {pane}) is left open for inspection - inspect it, then retire --force it or close it", err=True)
        raise
    typer.echo(f"restore registered: {' '.join(resume_argv_for(conf, session))}")
    log_event(root, event="spawn", member=name, by=caller, pane=pane, tab=tab_id,
              launcher=launcher, session=session)
    typer.echo(f"spawned {name} in tab {tab_id} (pane {pane}) through launcher {launcher}")


@app.command()
def restart(
    member: Annotated[str, typer.Argument(metavar="MEMBER", help="The member to relaunch")],
    reason: Annotated[str | None, typer.Option(help="Why - lands in the member's wake line and the log")] = None,
    force: Annotated[bool, typer.Option("--force", help="Restart even a live turn whose transcript moved within the last 10 minutes")] = False,
) -> None:
    """Relaunch MEMBER's own session in its pane through its recorded launcher, resuming its conversation."""
    root = mailbox_root()
    caller = own_name(root)
    restart_member(root, member_or_fail(root, member), caller, reason or "", force=force)


@app.command()
def inspect(
    member: Annotated[str, typer.Argument(metavar="MEMBER", help="The member to look at")],
    lines: Annotated[int, typer.Option(help="How many trailing pane lines to print")] = 40,
) -> None:
    """Show why MEMBER is not progressing: herdr state, pane tail, transcript age, mail, launcher, heartbeat. Read-only; needs no join."""
    root = mailbox_root()
    m = member_or_fail(root, member)
    if m.seat is None:
        typer.echo("seat: none recorded - the member is not running from any pane this mesh knows")
    else:
        pane = m.seat.pane
        record = agent_record_for_pane(pane)
        if record:
            typer.echo(f"herdr: {record.get('agent_status')} ({record.get('agent')}) in pane {pane}")
            try:
                explained = json.loads(herdr("agent", "explain", pane, "--json"))
                rule = (explained.get("matched_rule") or {}).get("id")
                if rule:
                    typer.echo(f"detection rule: {rule}")
            except (HerdrError, json.JSONDecodeError):
                pass
        else:
            typer.echo(f"herdr: no live agent at the member's seat (pane {pane})")
        try:
            typer.echo("--- pane tail ---")
            typer.echo(herdr("pane", "read", "--source", "recent-unwrapped", "--lines", str(lines), pane))
        except HerdrError as exc:
            typer.echo(f"pane read failed: {exc}")
    unread = len(messages_in(root / "inboxes" / m.name, strict=False))
    inflight = len(messages_in(root / "inboxes" / m.name / "inflight", strict=False))
    typer.echo(f"mail: unread {unread}  inflight {inflight}")
    if m.harness == "claude" and m.harness_session:
        last_write = transcript_last_write(m.harness_session)
        if last_write is None:
            typer.echo("transcript: none found on disk")
        else:
            typer.echo(f"transcript: last write {time.time() - last_write:.0f}s ago")
    launchers = load_launchers(root, required=False)
    if m.launcher is None:
        typer.echo("launcher: none recorded")
    else:
        conf = launchers.get(m.launcher)
        billed = f"billed={'true' if conf.billed else 'false'}" if conf else "unknown launcher - absent from launchers.toml"
        typer.echo(f"launcher: {m.launcher} ({billed})")
    state = heartbeat_state_if_any(root)
    if state is not None:
        watched = (state.get("members") or {}).get(m.name)
        if watched:
            typer.echo(f"heartbeat: {json.dumps(watched.get('last_fire'), sort_keys=True)}")


@app.command()
def interrupt(
    member: Annotated[str, typer.Argument(metavar="MEMBER", help="The member whose turn is stopped")],
    line: Annotated[str | None, typer.Argument(help="A line to submit once the turn is stopped")] = None,
) -> None:
    """Stop MEMBER's turn safely (composer guard, then Escape) and hand it LINE."""
    root = mailbox_root()
    caller = own_name(root)
    m = member_or_fail(root, member)
    outcome: tuple[RingOutcome, str] | None
    try:
        outcome = interrupt_seat(m, line, f"interrupt {member}")
    except InterruptUnconfirmed as exc:
        fail(str(exc))
    fired = "interrupted"
    if outcome is not None:
        ring_outcome, evidence = outcome
        if evidence:
            typer.echo(f"readback: {evidence}")
        fired = str(ring_outcome)
        typer.echo(f"{member}: {SEAT_DEFERRED.get(ring_outcome, ring_outcome)}")
    else:
        typer.echo(f"{member}: interrupted")
    log_event(root, event="interrupt", member=member, by=caller, outcome=fired)
    if outcome is not None and outcome[0] in SEAT_DEFERRED:
        raise typer.Exit(3)


@app.command()
def retire(
    member: Annotated[str, typer.Argument(metavar="MEMBER", help="The member to end - one you spawned")],
    force: Annotated[bool, typer.Option("--force", help="Retire despite unread or inflight mail")] = False,
) -> None:
    """End MEMBER - one you spawned - and remove it from the mesh, keeping its record under retired/."""
    root = mailbox_root()
    caller = own_name(root)
    m = member_or_fail(root, member)
    if m.spawned_by != caller:
        spawner = m.spawned_by or "nobody (it joined itself)"
        fail(f"{member} was spawned by {spawner}, not by you ({caller}); retire only members you spawned")
    unread = messages_in(root / "inboxes" / m.name, strict=False)
    inflight = messages_in(root / "inboxes" / m.name / "inflight", strict=False)
    if (unread or inflight) and not force:
        fail(f"{member} holds {len(unread)} unread and {len(inflight)} inflight messages; pass --force to retire it anyway")
    if m.seat is not None:
        exit_agent_in_place(m, f"retire {member}")
    if m.tab is not None:
        herdr("tab", "close", m.tab)
    retired = root / "retired"
    retired.mkdir(parents=True, exist_ok=True)
    target = retired / m.name
    if target.exists():
        fail(f"a retired record already exists at {target}; delete it first if the name is being reused")
    (root / "members" / m.name).rename(target)
    log_event(root, event="retire", member=member, by=caller, tab=m.tab)
    typer.echo(f"retired {member}; its record is {target}")


@app.command()
def adopt(
    member: Annotated[str, typer.Argument(metavar="MEMBER", help="The member to record a launcher for")],
    launcher: Annotated[str, typer.Option(help="The launchers.toml id to record")],
) -> None:
    """Record LAUNCHER on MEMBER after checking herdr's detected harness matches it."""
    root = mailbox_root()
    caller = own_name(root)
    m = member_or_fail(root, member)
    launchers = load_launchers(root, required=True)
    if launcher not in launchers:
        fail(f"launcher {launcher!r} is not in {root / 'launchers.toml'}; known: {sorted(launchers)}")
    conf = launchers[launcher]
    if m.seat is None:
        fail(f"{member} records no seat - adopt needs a live agent to check the harness against")
    record = agent_record_for_pane(m.seat.pane)
    if not record:
        fail(f"{member}'s pane holds no live agent to check the harness against")
    detected = record.get("agent")
    if detected != conf.harness:
        fail(f"herdr detects {detected!r} at {member}'s seat, but launcher {launcher!r} declares {conf.harness!r}")
    write_member(root, replace(m, launcher=launcher))
    log_event(root, event="adopt", member=member, by=caller, launcher=launcher)
    typer.echo(f"adopted {member} onto launcher {launcher}")


# --- heartbeat: an opt-in stall watchdog for a mesh ---------------------------------
#
# A per-mesh policy file (heartbeat.toml) maps each member to the checks that
# apply to it and the action each one takes, out of a small fixed vocabulary.
# The loop calls no model: herdr's event socket feeds a pure watcher core that
# arms deadlines, and an action runs only when a configured check fires.

HEARTBEAT_INTERVAL_DEFAULT_S = 5 * 60
HEARTBEAT_INTERVAL_MIN_S = 60
HEARTBEAT_LOCK_FILE = "heartbeat.lock"
HEARTBEAT_STATE_FILE = "heartbeat-state.json"
# the loop's wake is capped so a signal (stop, reload) is seen within a second;
# the deadline computation below narrows it further when a firing is due
HEARTBEAT_POLL_CAP_S = 1.0
HEARTBEAT_CONNECT_TIMEOUT_S = 10.0
HEARTBEAT_CATCHUP_FAILURES_MAX = 3
STOP_RELEASE_WAIT_S = 10.0
STOP_RELEASE_POLL_S = 0.2
# herdr socket protocol versions this client speaks; an unknown one refuses to start
SUPPORTED_HERDR_PROTOCOLS = (22,)
# herdr detection rules whose "working" is a designed wait, never a hang
DESIGNED_WAIT_RULES = ("background_agents_working", "background_mcp_task_working")
# the default `unless` list: pane text that marks a designed wait
DEFAULT_UNLESS = ("Waiting for", "background agent")

DURATION_RE = re.compile(r"^(\d+)([smh])$")
DURATION_UNITS = {"s": 1, "m": 60, "h": 3600}
HEARTBEAT_CHECKS = ("unread", "idle", "hung", "blocked", "error")
HEARTBEAT_ACTIONS = ("poke", "ring", "interrupt", "notify", "restart", "log")
RULE_KEYS = ("do", "after", "match", "unless", "text", "to")


def parse_duration(text: str) -> float | None:
    """Seconds for `<integer><s|m|h>`, or None when the text is not a duration."""
    match = DURATION_RE.fullmatch(str(text))
    return int(match.group(1)) * DURATION_UNITS[match.group(2)] if match else None


def heartbeat_policy_path(root: Path) -> Path:
    return root / "heartbeat.toml"


@dataclass(frozen=True, slots=True)
class Rule:
    """One configured check->action pair for one member."""

    check: str
    action: str
    after: float | None = None  # seconds; None for the event-driven error check
    match: tuple[str, ...] = ()
    unless: tuple[str, ...] = ()
    text: str | None = None
    to: str | None = None


@dataclass(frozen=True, slots=True)
class HeartbeatPolicy:
    interval: float
    escalate_to: str | None
    rules: dict[str, tuple[Rule, ...]]  # member name -> its rules; a member absent here is never acted on


def parse_policy(
    text: str, path: Path, member_by_name: dict[str, Member]
) -> tuple[HeartbeatPolicy | None, list[str]]:
    """(policy, problems); the loaders fail loudly on any problem, naming the offending key."""
    problems: list[str] = []
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return None, [f"{path} is not valid TOML: {exc}"]
    if not isinstance(doc, dict):
        return None, [f"{path} must be a table"]
    unknown_top = sorted(set(doc) - {"interval", "escalate_to", "member"})
    if unknown_top:
        problems.append(f"{path}: unknown top-level keys {unknown_top}; allowed: interval, escalate_to, member")
    interval = HEARTBEAT_INTERVAL_DEFAULT_S
    if "interval" in doc:
        raw = doc["interval"]
        seconds = parse_duration(raw) if isinstance(raw, str) else None
        if seconds is None:
            problems.append(f"{path}: interval {raw!r} must be a duration like 5m")
        elif seconds < HEARTBEAT_INTERVAL_MIN_S:
            problems.append(f"{path}: interval {raw!r} must be at least 1m")
        else:
            interval = seconds
    escalate_to = doc.get("escalate_to")
    if escalate_to is not None and escalate_to not in member_by_name:
        problems.append(f"{path}: escalate_to {escalate_to!r} is not a mesh member; members are {sorted(member_by_name)}")
        escalate_to = None
    rules: dict[str, tuple[Rule, ...]] = {}
    tables = doc.get("member", {})
    if not isinstance(tables, dict):
        problems.append(f"{path}: member must be a table of [member.<name>] tables")
        tables = {}
    for name, table in tables.items():
        m = member_by_name.get(name)
        if m is None:
            problems.append(f"{path}: [member.{name}] is not a mesh member; members are {sorted(member_by_name)}")
            continue
        where = f"{path}: [member.{name}]"
        if not isinstance(table, dict):
            problems.append(f"{where} must be a table of checks")
            continue
        unknown = sorted(set(table) - set(HEARTBEAT_CHECKS))
        if unknown:
            problems.append(f"{where} has unknown checks {unknown}; allowed: {list(HEARTBEAT_CHECKS)}")
        member_rules = []
        for check, spec in table.items():
            if check not in HEARTBEAT_CHECKS:
                continue
            cwhere = f"{where}.{check}"
            if not isinstance(spec, dict):
                problems.append(f'{cwhere} must be a table like {{after = "10m", do = "poke"}}')
                continue
            unknown_c = sorted(set(spec) - set(RULE_KEYS))
            if unknown_c:
                problems.append(f"{cwhere} has unknown keys {unknown_c}; allowed: {list(RULE_KEYS)}")
            do = spec.get("do")
            if do not in HEARTBEAT_ACTIONS:
                problems.append(f"{cwhere} do {do!r} is not one of {list(HEARTBEAT_ACTIONS)}")
                continue
            bad = False
            after: float | None = None
            match: tuple[str, ...] = ()
            unless: tuple[str, ...] = ()
            text: str | None = None
            to: str | None = None
            if check == "error":
                raw_match = spec.get("match")
                if isinstance(raw_match, str):
                    raw_match = [raw_match]
                if not (isinstance(raw_match, list) and raw_match and all(isinstance(x, str) and x for x in raw_match)):
                    problems.append(f"{cwhere} requires match - a string or list of strings")
                    bad = True
                else:
                    match = tuple(raw_match)
            else:
                seconds = parse_duration(spec.get("after")) if isinstance(spec.get("after"), str) else None
                if seconds is None:
                    problems.append(f"{cwhere} requires after - a duration like 30m")
                    bad = True
                else:
                    after = seconds
            if check == "hung":
                raw_unless = spec.get("unless")
                if raw_unless is None:
                    raw_unless = list(DEFAULT_UNLESS)
                elif isinstance(raw_unless, str):
                    raw_unless = [raw_unless]
                if isinstance(raw_unless, list) and all(isinstance(x, str) for x in raw_unless):
                    unless = tuple(raw_unless)
                if m.harness != "claude":
                    problems.append(
                        f"{cwhere} hung is defined only for claude members; {name} records harness {m.harness!r}"
                    )
                    bad = True
            if do in ("ring", "interrupt"):
                if not isinstance(spec.get("text"), str) or not spec["text"]:
                    problems.append(f"{cwhere} do {do!r} requires text")
                    bad = True
                else:
                    text = spec["text"]
            if do == "interrupt" and m.harness != "claude":
                problems.append(
                    f"{cwhere} interrupt is valid only where Escape interrupts a turn (claude members);"
                    f" {name} records harness {m.harness!r}"
                )
                bad = True
            if do == "notify":
                if spec.get("to") not in member_by_name or spec.get("to") in RESERVED_NAMES:
                    problems.append(f"{cwhere} notify requires to - an existing mesh member")
                    bad = True
                else:
                    to = spec["to"]
            if do == "restart" and m.launcher is None:
                problems.append(
                    f"{cwhere} restart requires a member with a recorded launcher; {name} records none"
                    " (see `mailbox adopt`)"
                )
                bad = True
            if bad:
                continue
            member_rules.append(Rule(check=check, action=do, after=after, match=match, unless=unless, text=text, to=to))
        if member_rules:
            rules[name] = tuple(member_rules)
    if problems:
        return None, problems
    return HeartbeatPolicy(interval=interval, escalate_to=escalate_to, rules=rules), []


def load_heartbeat_policy(root: Path, *, required: bool) -> HeartbeatPolicy | None:
    """The mesh's validated heartbeat policy; None when no heartbeat.toml exists."""
    path = heartbeat_policy_path(root)
    if not path.is_file():
        if required:
            fail(
                f"{path} is missing - the heartbeat is off for this mesh; create one with"
                f" `{root / 'bin' / 'mailbox'} heartbeat init --template <name>`"
            )
        return None
    policy, problems = parse_policy(path.read_text(), path, {m.name: m for m in members(root)})
    if problems:
        fail("; ".join(problems))
    return policy


# the shipped templates; heartbeat init writes one, refusing to overwrite

def overseer_worker_template(overseer: str, worker: str) -> str:
    return f'''interval = "5m"
escalate_to = "{overseer}"

[member.{worker}]
unread  = {{ after = "10m", do = "poke" }}
idle    = {{ after = "60m", do = "ring", text = "heartbeat: idle 60+ min. Continue unfinished work, set a wake on running jobs, or mail the overseer if blocked. Otherwise end the turn." }}
hung    = {{ after = "30m", do = "interrupt", text = "heartbeat: your turn hung and was interrupted; resume where you left off." }}
blocked = {{ after = "30m", do = "notify", to = "{overseer}" }}
error   = {{ match = ["issue with the selected model", "API Error"], do = "notify", to = "{overseer}" }}

[member.{overseer}]
unread = {{ after = "15m", do = "poke" }}
hung   = {{ after = "30m", do = "interrupt", text = "heartbeat: your turn hung and was interrupted; continue." }}
'''


def peers_template(roster: list[Member]) -> str:
    lines = ['interval = "5m"', ""]
    for m in roster:
        lines.append(f"[member.{m.name}]")
        lines.append('unread = { after = "10m", do = "poke" }')
        if m.harness == "claude":
            lines.append(
                'hung = { after = "30m", do = "interrupt",'
                ' text = "heartbeat: your turn hung and was interrupted; resume where you left off." }'
            )
        lines.append("")
    return "\n".join(lines)


def log_only_template(roster: list[Member]) -> str:
    lines = ['interval = "5m"', ""]
    for m in roster:
        lines.append(f"[member.{m.name}]")
        lines.append('unread  = { after = "10m", do = "log" }')
        lines.append('idle    = { after = "60m", do = "log" }')
        lines.append('blocked = { after = "30m", do = "log" }')
        lines.append('error   = { match = ["issue with the selected model", "API Error"], do = "log" }')
        if m.harness == "claude":
            lines.append('hung    = { after = "30m", do = "log" }')
        lines.append("")
    return "\n".join(lines)


# the pure watcher core: (policy, state, input, now) -> firings. Owns no I/O,
# takes an injected clock, and is tested directly with event sequences.

@dataclass(slots=True)
class Episode:
    """One check's firing history inside a continuous stretch of the condition holding.

    Fires twice, escalates once on the third due firing, then stays silent until
    the condition ends - so an episode fires at most three times."""

    fires: int = 0
    escalated: bool = False
    silent: bool = False
    last_fire: float | None = None


@dataclass(slots=True)
class WatchState:
    """One watched member's observed state."""

    status: str | None = None
    status_since: float | None = None  # when the current status was entered under observation
    absent: bool = False
    unread_oldest: float | None = None  # mtime of the oldest unread file, when unread was observed
    unread_count: int = 0
    pane_text: str = ""
    transcript_write: float | None = None
    designed_wait: bool = False
    designed_wait_left_at: float | None = None  # hung time starts over from here after a designed wait
    episodes: dict[str, Episode] = field(default_factory=dict)
    last_fire: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Observation:
    """One member's directly observed state, from herdr, the inbox and the transcript."""

    status: str | None  # None: no live agent at the seat (absent)
    unread_oldest: float | None
    unread_count: int
    transcript_write: float | None
    pane_text: str = ""
    designed_wait: bool = False


@dataclass(frozen=True, slots=True)
class Firing:
    member: str
    rule: Rule
    escalated: bool
    evidence: str


class Watcher:
    """The pure watcher core: deadlines armed and cancelled by events, firings evaluated
    against the policy, cooldown and episode."""

    def __init__(self, policy: HeartbeatPolicy, clock: Callable[[], float]):
        self.policy = policy
        self.clock = clock
        self.states: dict[str, WatchState] = {name: WatchState() for name in policy.rules}

    def on_status(self, member: str, status: str, now: float) -> None:
        st = self.states[member]
        st.absent = False
        if status != st.status:
            st.status = status
            st.status_since = now

    def on_absent(self, member: str, now: float) -> None:
        self.states[member].absent = True

    def observe(self, member: str, obs: Observation, now: float) -> list[str]:
        """Reconcile one catch-up observation; returns this member's absent/present transitions."""
        st = self.states[member]
        transitions: list[str] = []
        if obs.status is None:
            if not st.absent:
                st.absent = True
                transitions.append("absent")
            return transitions
        if st.absent:
            st.absent = False
            transitions.append("present")
        if obs.status != st.status:
            st.status = obs.status
            st.status_since = now
        st.unread_oldest = obs.unread_oldest
        st.unread_count = obs.unread_count
        st.pane_text = obs.pane_text
        st.transcript_write = obs.transcript_write
        if obs.designed_wait and not st.designed_wait:
            st.designed_wait = True
        elif not obs.designed_wait and st.designed_wait:
            st.designed_wait = False
            # leaving a designed wait re-arms the hung clock from this moment
            st.designed_wait_left_at = now
        return transitions

    def on_match(self, member: str, line: str, now: float) -> list[Firing]:
        """An output-match event: each matching error rule evaluates its full holding
        condition. A match printed while working is left for the catch-up pass."""
        st = self.states[member]
        if st.absent or st.status != "idle":
            return []
        firings = []
        for rule in self.policy.rules[member]:
            if rule.check != "error":
                continue
            if not any(pattern.lower() in line.lower() for pattern in rule.match):
                continue
            firing = self._consider(member, rule, now, evidence=f"pane printed {line[:120]!r}")
            if firing is not None:
                firings.append(firing)
        return firings

    def holds(self, member: str, rule: Rule, now: float) -> str | None:
        """Evidence when the rule's condition holds at NOW, else None."""
        st = self.states[member]
        if st.absent or st.status is None:
            return None
        if rule.check == "unread":
            if st.status != "idle" or st.unread_oldest is None or rule.after is None:
                return None
            age = now - st.unread_oldest
            return f"oldest unread {age:.0f}s old (after {rule.after:.0f}s)" if age >= rule.after else None
        if rule.check == "idle":
            if st.status != "idle" or st.unread_count or st.status_since is None or rule.after is None:
                return None
            age = now - st.status_since
            return f"idle {age:.0f}s (after {rule.after:.0f}s)" if age >= rule.after else None
        if rule.check == "hung":
            if st.status != "working" or st.designed_wait or st.transcript_write is None or rule.after is None:
                return None
            age = now - max(st.transcript_write, st.designed_wait_left_at or st.transcript_write)
            return f"working, transcript quiet {age:.0f}s (after {rule.after:.0f}s)" if age >= rule.after else None
        if rule.check == "blocked":
            if st.status != "blocked" or st.status_since is None or rule.after is None:
                return None
            age = now - st.status_since
            return f"blocked {age:.0f}s (after {rule.after:.0f}s)" if age >= rule.after else None
        if rule.check == "error":
            if st.status != "idle" or not rule.match:
                return None
            hit = next((pattern for pattern in rule.match if pattern.lower() in st.pane_text.lower()), None)
            return f"pane shows {hit!r}" if hit else None
        return None

    def cooldown(self, rule: Rule) -> float:
        # a duration check re-arms for another `after`; error re-arms after the
        # catch-up interval, so one stuck error screen does not fire on every repaint
        return self.policy.interval if rule.check == "error" else (rule.after or 0.0)

    def _consider(self, member: str, rule: Rule, now: float, evidence: str | None = None) -> Firing | None:
        st = self.states[member]
        holds = self.holds(member, rule, now) if evidence is None else evidence
        episode = st.episodes.setdefault(rule.check, Episode())
        if holds is None:
            # the condition ended: the episode is over and the next stretch starts fresh
            if episode.fires or episode.silent:
                st.episodes[rule.check] = Episode()
            return None
        if episode.silent:
            return None
        if episode.last_fire is not None and now < episode.last_fire + self.cooldown(rule):
            return None
        if episode.fires >= 2:
            episode.escalated = True
            episode.silent = True
            episode.last_fire = now
            return Firing(member=member, rule=rule, escalated=True, evidence=holds)
        episode.fires += 1
        episode.last_fire = now
        return Firing(member=member, rule=rule, escalated=False, evidence=holds)

    def due(self, now: float) -> list[Firing]:
        return [
            firing
            for member in self.policy.rules
            for firing in (self._consider(member, rule, now) for rule in self.policy.rules[member])
            if firing is not None
        ]

    def undo_fire(self, member: str, check: str, now: float) -> None:
        """Take back a firing whose action did not land, so it retries at the next pass."""
        episode = self.states[member].episodes.get(check)
        if episode is None:
            return
        if episode.escalated:
            episode.escalated = False
            episode.silent = False
        elif episode.fires:
            episode.fires -= 1
        if episode.last_fire is not None:
            # retry at the next catch-up pass, the cooldown still running
            rule = next(r for r in self.policy.rules[member] if r.check == check)
            episode.last_fire = now - self.cooldown(rule) + self.policy.interval

    def rearm_hung(self, member: str, transcript_write: float | None) -> bool:
        """A due hung firing whose transcript moved is rearmed, not fired."""
        st = self.states[member]
        if transcript_write is not None and (st.transcript_write is None or transcript_write > st.transcript_write):
            st.transcript_write = transcript_write
            return True
        return False

    def next_deadline(self) -> float | None:
        """The earliest time anything can next fire, or None - the loop's wake computation."""
        now = self.clock()
        best: float | None = None
        for member, rules in self.policy.rules.items():
            st = self.states[member]
            for rule in rules:
                episode = st.episodes.get(rule.check)
                candidate = None
                if episode is not None and episode.last_fire is not None:
                    candidate = episode.last_fire + self.cooldown(rule)
                elif rule.after is not None:
                    if rule.check == "unread" and st.unread_oldest is not None:
                        candidate = st.unread_oldest + rule.after
                    elif rule.check == "idle" and st.status == "idle" and st.status_since is not None:
                        candidate = st.status_since + rule.after
                    elif rule.check == "blocked" and st.status == "blocked" and st.status_since is not None:
                        candidate = st.status_since + rule.after
                    elif rule.check == "hung" and st.status == "working" and st.transcript_write is not None:
                        candidate = max(st.transcript_write, st.designed_wait_left_at or st.transcript_write) + rule.after
                if candidate is not None and (best is None or candidate < best):
                    best = candidate
        return best

    def record_fire(self, member: str, rule: Rule, outcome: str, now: float) -> None:
        self.states[member].last_fire[rule.check] = {
            "time": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(timespec="seconds"),
            "action": rule.action,
            "outcome": outcome,
        }


# the I/O half: observations, actions, the socket client, the loop, the lock

def observe_member(root: Path, member: Member | None, rules: tuple[Rule, ...]) -> Observation:
    """One member's observed state: herdr status, inbox ages, transcript age, pane text."""
    if member is None or member.seat is None:
        return Observation(status=None, unread_oldest=None, unread_count=0, transcript_write=None)
    record = agent_record_for_pane(member.seat.pane)
    if not record:
        return Observation(status=None, unread_oldest=None, unread_count=0, transcript_write=None)
    unread = messages_in(root / "inboxes" / member.name, strict=False)
    oldest = min((message.path.stat().st_mtime for message in unread), default=None)
    transcript = (
        transcript_last_write(member.harness_session)
        if member.harness == "claude" and member.harness_session else None
    )
    pane_text = ""
    designed = False
    # the pane is read only when a rule needs its text: error matches and hung's
    # designed-wait markers
    if any(rule.check in ("error", "hung") for rule in rules):
        try:
            pane_text = herdr("pane", "read", "--source", "visible", member.seat.pane)
        except HerdrError:
            pane_text = ""
        designed = designed_wait(member.seat.pane, pane_text, rules)
    return Observation(
        status=record.get("agent_status"),
        unread_oldest=oldest,
        unread_count=len(unread),
        transcript_write=transcript,
        pane_text=pane_text,
        designed_wait=designed,
    )


def designed_wait(pane: str, pane_text: str, rules: tuple[Rule, ...]) -> bool:
    """True when the member's "working" is a wait by design: herdr's matched detection
    rule is a background-wait rule, or the pane text carries an `unless` marker."""
    hung_rules = [rule for rule in rules if rule.check == "hung"]
    if not hung_rules:
        return False
    try:
        explained = json.loads(herdr("agent", "explain", pane, "--json"))
        rule_id = (explained.get("matched_rule") or {}).get("id")
        if rule_id in DESIGNED_WAIT_RULES:
            return True
    except (HerdrError, json.JSONDecodeError):
        pass
    lowered = pane_text.lower()
    return any(marker.lower() in lowered for rule in hung_rules for marker in (rule.unless or DEFAULT_UNLESS))


def heartbeat_notify(root: Path, to: str, slug: str, body: str) -> None:
    """Write one message from the reserved sender `heartbeat`, then ring the recipient."""
    seq = f"{next_seq(root, 'heartbeat'):0{SEQ_WIDTH}d}"
    msg_id = f"{seq}-{slug}"
    write_messages(root, "heartbeat", msg_id, Kind.MSG, body, [to])
    member = member_named(root, to)
    log_event(root, event="sent", sender="heartbeat", session=member.harness_session if member else None,
              id=msg_id, kind="msg", to=[to])
    ring(root, to)


def raise_herdr_notification(title: str, body: str) -> None:
    """A best-effort human channel: the worst case it covers - nobody reading the log -
    is exactly when the loop must still reach a person."""
    try:
        herdr("notification", "show", title, "--body", body[:240])
    except (HerdrError, OSError):
        pass


def run_firing(root: Path, firing: Firing, policy: HeartbeatPolicy, *, dry_run: bool) -> tuple[str, bool]:
    """(outcome line, effective) for one firing. The heartbeat is not a joined member,
    so it calls the shared internals - the ring, the message writer, the restart core -
    with the caller identity `heartbeat`, never the member-facing verbs.

    An action that does not land (a ring that stayed unsubmitted) returns
    effective=False so the loop takes the firing back and retries next pass."""
    rule = firing.rule
    if dry_run:
        action = "escalate" if firing.escalated else rule.action
        return f"would {action}: {firing.evidence}", True
    member = member_named(root, firing.member)
    if member is None or member.seat is None:
        return "member has no live record", False
    pane = member.seat.pane
    try:
        if firing.escalated:
            if policy.escalate_to:
                body = (
                    f"heartbeat needs a human: {firing.member}'s {rule.check} check is still"
                    f" holding after two firings.\ncheck: {rule.check} ({rule.action})\n"
                    f"evidence: {firing.evidence}\npane: {pane}\n"
                )
                heartbeat_notify(root, policy.escalate_to, f"escalate-{rule.check}", body)
            raise_herdr_notification(
                f"mailbox heartbeat: {firing.member} {rule.check}",
                f"still holding: {firing.evidence}",
            )
            return "needs-human", True
        if rule.action == "poke":
            if not messages_in(root / "inboxes" / firing.member, strict=False):
                return "nothing to poke", True
            outcome, _ = ring(root, firing.member)
            return str(outcome), outcome is RingOutcome.RUNG
        if rule.action == "ring":
            outcome, evidence = ring_seat(pane, f"{rule.text} - contract: ../../README.md", wait_ms=MAIL_RING_WAIT_MS)
            return f"{outcome}" + (f"; {evidence}" if evidence else ""), outcome in (RingOutcome.RUNG, RingOutcome.QUEUED)
        if rule.action == "interrupt":
            interrupt_seat(member, f"{rule.text} - contract: ../../README.md", f"heartbeat interrupt {firing.member}")
            return "interrupted", True
        if rule.action == "notify":
            body = (
                f"heartbeat: {firing.member} tripped its {rule.check} check.\n"
                f"evidence: {firing.evidence}\npane: {pane}\n"
            )
            heartbeat_notify(root, rule.to, f"{rule.check}-{firing.member}", body)
            return f"notified {rule.to}", True
        if rule.action == "restart":
            restart_member(root, member, "heartbeat", f"heartbeat: {rule.check} ({firing.evidence})", force=False)
            return "restarted", True
        return "logged", True
    except InterruptUnconfirmed as exc:
        # the ring is not sent; the firing still counts, so the episode continues toward escalation
        return f"interrupt-unconfirmed ({exc})", True
    except typer.Exit:
        return "action failed - see the pane output", False
    except HerdrError as exc:
        return f"herdr error: {exc.code}", False


# herdr exposes events.subscribe only on its socket, never as a CLI verb; the
# helper speaks the newline-delimited JSON protocol directly

class EventsLost(Exception):
    """herdr dropped retained history for this subscriber; reconnect and catch up."""


class ConnectionDropped(Exception):
    """herdr closed the subscription connection."""


class HerdrProtocolError(Exception):
    """herdr refused the subscription or spoke an unknown protocol."""


class EventsConnection:
    """One events.subscribe request on herdr's socket, then the pushed envelopes."""

    def __init__(self, path: Path, subscriptions: list[dict[str, Any]]):
        self.path = path
        self.subscriptions = subscriptions
        self.sub_id = "mailbox-heartbeat"
        self.sock: socket.socket | None = None
        self.buffer = b""

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(str(self.path))
        self.buffer = b""
        request = {"id": self.sub_id, "method": "events.subscribe",
                   "params": {"subscriptions": self.subscriptions}}
        self.sock.sendall(json.dumps(request).encode() + b"\n")
        # the first response only acknowledges the subscription; events follow
        response = json.loads(self._read_line(HEARTBEAT_CONNECT_TIMEOUT_S))
        if "error" in response:
            error = response["error"]
            raise HerdrProtocolError(f"herdr refused the subscription: {error.get('code')}: {error.get('message')}")

    def _read_line(self, timeout_s: float) -> bytes:
        assert self.sock is not None
        while b"\n" not in self.buffer:
            readable, _, _ = select.select([self.sock], [], [], timeout_s)
            if not readable:
                raise HerdrProtocolError(f"no subscription acknowledgement from herdr within {timeout_s:g}s")
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionDropped(f"herdr closed {self.path}")
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        return line

    def next_event(self, timeout_s: float) -> dict[str, Any] | None:
        """The next pushed subscription envelope, or None within TIMEOUT_S."""
        assert self.sock is not None
        while b"\n" not in self.buffer:
            readable, _, _ = select.select([self.sock], [], [], timeout_s)
            if not readable:
                return None
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionDropped(f"herdr closed {self.path}")
            self.buffer += chunk
            timeout_s = 0.0  # buffered bytes must not wait again
        line, self.buffer = self.buffer.split(b"\n", 1)
        envelope = json.loads(line)
        if "error" in envelope:
            error = envelope["error"]
            if error.get("code") == "events_lost":
                raise EventsLost(error.get("message", "events_lost"))
            raise HerdrProtocolError(f"subscription error {error.get('code')}: {error.get('message')}")
        return envelope

    def close(self) -> None:
        if self.sock is not None:
            with contextlib.suppress(OSError):
                self.sock.close()
            self.sock = None


def herdr_socket() -> tuple[Path, int]:
    """(socket path, protocol version) of this session's herdr server, from `herdr status`."""
    status = json.loads(herdr("status", "--json"))
    server = status.get("server") or {}
    return Path(server["socket"]), int(server.get("protocol") or 0)


def heartbeat_subscriptions(policy: HeartbeatPolicy, member_by_name: dict[str, Member]) -> list[dict[str, Any]]:
    """One status subscription per watched seat, one output-match subscription per
    configured error pattern."""
    subscriptions: list[dict[str, Any]] = []
    for name in policy.rules:
        member = member_by_name.get(name)
        if member is None or member.seat is None:
            continue
        subscriptions.append({"type": "pane.agent_status_changed", "pane_id": member.seat.pane})
        for rule in policy.rules[name]:
            if rule.check != "error":
                continue
            for pattern in rule.match:
                subscriptions.append({
                    "type": "pane.output_matched", "pane_id": member.seat.pane,
                    "source": "visible", "match": {"type": "substring", "value": pattern},
                })
    return subscriptions


class HeartbeatLoop:
    """The foreground loop: events and catch-up observations feed the watcher core,
    actions run one at a time, and the lock is held for the loop's whole lifetime."""

    def __init__(
        self,
        root: Path,
        policy: HeartbeatPolicy,
        *,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        connect: Callable[[Path, list[dict[str, Any]]], EventsConnection] = EventsConnection,
        socket_info: Callable[[], tuple[Path, int]] = herdr_socket,
    ) -> None:
        self.root = root
        self.policy = policy
        self.policy_text = heartbeat_policy_path(root).read_text() if heartbeat_policy_path(root).is_file() else ""
        self.clock = clock
        self.sleep = sleep
        self.connect = connect
        self.socket_info = socket_info
        self.watcher = Watcher(policy, clock)
        self.connection: EventsConnection | None = None
        self.current_subs: list[dict[str, Any]] = []
        self.pane_to_member: dict[str, str] = {}
        self.connected = False
        self.reload_flag = False
        self.stopping = False
        self.stopped_note = False
        self.started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.last_pass: float | None = None
        self.failures = 0

    def note(self, *, log: bool = True, **event: object) -> None:
        """One line in the heartbeat pane and one heartbeat log event (no log when dry)."""
        rendered = " ".join(f"{key}={value}" for key, value in event.items() if value is not None)
        typer.echo(f"heartbeat: {rendered}")
        if log:
            log_event(self.root, event="heartbeat", **event)

    def refresh_roster(self) -> dict[str, Member]:
        records = {m.name: m for m in members(self.root)}
        self.pane_to_member = {
            m.seat.pane: name
            for name, m in records.items()
            if name in self.policy.rules and m.seat is not None
        }
        return records

    def ensure_connected(self) -> None:
        if self.connected:
            return
        path, protocol = self.socket_info()
        if protocol not in SUPPORTED_HERDR_PROTOCOLS:
            fail(
                f"herdr speaks socket protocol {protocol}; this helper supports only"
                f" {SUPPORTED_HERDR_PROTOCOLS} - refusing to run the heartbeat against an unknown protocol"
            )
        records = self.refresh_roster()
        subs = heartbeat_subscriptions(self.policy, records)
        connection = self.connect(path, subs)
        try:
            connection.connect()
        except (HerdrProtocolError, EventsLost, ConnectionDropped):
            connection.close()
            raise
        self.connection = connection
        self.current_subs = subs
        self.connected = True

    def disconnect(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        self.connected = False

    def catchup(self, dry_run: bool = False) -> bool:
        """One reconciliation pass over every watched member; False when any observation failed."""
        records = self.refresh_roster()
        # the pass re-resolves seats; a member whose pane id changed is re-subscribed
        subs = heartbeat_subscriptions(self.policy, records)
        if self.connected and subs != self.current_subs:
            self.disconnect()
            self.ensure_connected()
        now = self.clock()
        ok = True
        for name in self.policy.rules:
            try:
                obs = observe_member(self.root, records.get(name), self.policy.rules[name])
            except HerdrError as exc:
                self.note(member=name, action="observe-error", outcome=exc.code)
                ok = False
                continue
            for transition in self.watcher.observe(name, obs, now):
                self.note(member=name, action=transition)
        self.fire_due(dry_run)
        self.last_pass = now
        self.failures = 0 if ok else self.failures + 1
        self.write_state()
        return ok

    def fire_due(self, dry_run: bool) -> None:
        for firing in self.watcher.due(self.clock()):
            self.run_firing(firing, dry_run)

    def run_firing(self, firing: Firing, dry_run: bool) -> None:
        # a due hung firing whose transcript moved is rearmed, not fired
        if firing.rule.check == "hung" and not dry_run:
            member = member_named(self.root, firing.member)
            if member is not None and member.harness == "claude" and member.harness_session:
                if self.watcher.rearm_hung(firing.member, transcript_last_write(member.harness_session)):
                    return
        outcome, effective = run_firing(self.root, firing, self.policy, dry_run=dry_run)
        if not effective:
            self.watcher.undo_fire(firing.member, firing.rule.check, self.clock())
        self.watcher.record_fire(firing.member, firing.rule, outcome, self.clock())
        action = "escalation" if firing.escalated else "firing"
        self.note(log=not dry_run, member=firing.member, action=action,
                  check=firing.rule.check, do=firing.rule.action, outcome=outcome,
                  evidence=firing.evidence)

    def handle_event(self, envelope: dict[str, Any], dry_run: bool) -> None:
        kind = envelope.get("event")
        data = envelope.get("data") or {}
        member = self.pane_to_member.get(data.get("pane_id"))
        if member is None:
            return
        now = self.clock()
        if kind == "pane.agent_status_changed":
            status = data.get("agent_status")
            if status is None:
                self.watcher.on_absent(member, now)
            else:
                self.watcher.on_status(member, status, now)
        elif kind == "pane.output_matched":
            for firing in self.watcher.on_match(member, data.get("matched_line") or "", now):
                self.run_firing(firing, dry_run)

    def reload_policy(self) -> None:
        """Re-read heartbeat.toml; an invalid edit keeps the last valid policy in force."""
        path = heartbeat_policy_path(self.root)
        if not path.is_file():
            self.note(action="stop", outcome="policy deleted")
            self.stopping = True
            self.stopped_note = True
            return
        text = path.read_text()
        self.policy_text = text
        policy, problems = parse_policy(text, path, {m.name: m for m in members(self.root)})
        if policy is None:
            self.note(action="config-error", outcome="; ".join(problems)[:500])
            return
        self.policy = policy
        # subscriptions and deadlines are rebuilt to match the new policy
        self.watcher = Watcher(policy, self.clock)
        self.disconnect()
        self.note(action="reload", outcome=f"{len(policy.rules)} members watched")

    def backoff_reconnect(self) -> None:
        delay = 0.5
        while not self.stopping:
            self.sleep(delay)
            delay = min(delay * 2, 30.0)
            try:
                self.ensure_connected()
                self.note(action="reconnected")
                # while disconnected the catch-up pass alone drove the checks;
                # a pass on reconnect repairs what a missed event left wrong
                self.catchup()
                return
            except (HerdrProtocolError, HerdrError, OSError, EventsLost, ConnectionDropped) as exc:
                self.note(action="reconnect-failed", outcome=str(exc)[:300])

    def write_state(self) -> None:
        state = {
            "started": self.started,
            "last_pass": (
                datetime.fromtimestamp(self.last_pass, tz=timezone.utc).isoformat(timespec="seconds")
                if self.last_pass is not None else None
            ),
            "connected": self.connected,
            "members": {
                name: {
                    "status": st.status,
                    "absent": st.absent,
                    "unread": st.unread_count,
                    "last_fire": st.last_fire,
                }
                for name, st in self.watcher.states.items()
            },
        }
        write_atomic(self.root / HEARTBEAT_STATE_FILE, json.dumps(state, indent=1) + "\n")

    def run(self, dry_run: bool = False) -> None:
        def on_term(signum: object, frame: object) -> None:
            self.stopping = True

        def on_hup(signum: object, frame: object) -> None:
            self.reload_flag = True

        previous_term = signal.signal(signal.SIGTERM, on_term)
        previous_hup = signal.signal(signal.SIGHUP, on_hup)
        self.ensure_connected()
        self.note(action="start", outcome=f"interval {self.policy.interval:.0f}s")
        next_pass = self.clock()
        try:
            while not self.stopping:
                now = self.clock()
                if self.reload_flag:
                    self.reload_flag = False
                    self.reload_policy()
                    if self.stopping:
                        break
                if now >= next_pass:
                    # the policy file is re-read at every pass; only a change reloads
                    path = heartbeat_policy_path(self.root)
                    if not path.is_file():
                        self.note(action="stop", outcome="policy deleted")
                        self.stopped_note = True
                        break
                    text = path.read_text()
                    if text != self.policy_text:
                        self.reload_policy()
                        if self.stopping:
                            break
                    self.catchup(dry_run)
                    if self.failures >= HEARTBEAT_CATCHUP_FAILURES_MAX:
                        self.note(action="stop", outcome="catch-up failed for every member three passes running")
                        raise typer.Exit(1)
                    next_pass = self.clock() + self.policy.interval
                    continue
                wake = min(max(next_pass - now, 0.0), HEARTBEAT_POLL_CAP_S)
                deadline = self.watcher.next_deadline()
                if deadline is not None:
                    wake = min(wake, max(deadline - now, 0.0))
                try:
                    if self.connected:
                        event = self.connection.next_event(wake)  # type: ignore[union-attr]
                    else:
                        self.sleep(wake)
                        event = None
                except (ConnectionDropped, EventsLost) as exc:
                    self.connected = False
                    self.note(action="disconnected", outcome=str(exc)[:300])
                    self.backoff_reconnect()
                    continue
                if event is not None:
                    self.handle_event(event, dry_run)
                else:
                    self.fire_due(dry_run)
        finally:
            self.write_state()
            self.disconnect()
            signal.signal(signal.SIGTERM, previous_term)
            signal.signal(signal.SIGHUP, previous_hup)
            if not self.stopped_note:
                self.note(action="stop", outcome="signal" if self.stopping else "loop ended")


class HeartbeatLock:
    """The mesh's exclusive heartbeat lock: an OS file lock held for the loop's lifetime.

    The OS releases it when the process dies, so "running" means only "the lock is
    held" - no PID guessing. The file records the holder's pid, pane and start
    time for `stop` and `status`."""

    def __init__(self, root: Path):
        self.path = root / HEARTBEAT_LOCK_FILE
        self.fd: int | None = None

    def acquire(self) -> "HeartbeatLock | LockInfo":
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            info = _read_lock_info(self.path)
            os.close(fd)
            return info
        info = {
            "pid": os.getpid(),
            "pane": os.environ.get("HERDR_PANE_ID"),
            "tab": os.environ.get("HERDR_TAB_ID"),
            "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, (json.dumps(info) + "\n").encode())
        self.fd = fd
        return self

    def release(self) -> None:
        if self.fd is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


@dataclass(frozen=True, slots=True)
class LockInfo:
    pid: int | None
    pane: str | None
    tab: str | None
    started: str | None


def _read_lock_info(path: Path) -> LockInfo:
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        raw = {}
    return LockInfo(
        pid=raw.get("pid"), pane=raw.get("pane"), tab=raw.get("tab"), started=raw.get("started")
    )


def heartbeat_lock_holder(root: Path) -> LockInfo | None:
    """The lock's holder while the lock is held, or None when no heartbeat runs."""
    path = root / HEARTBEAT_LOCK_FILE
    if not path.is_file():
        return None
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return None
    except OSError:
        return _read_lock_info(path)
    finally:
        os.close(fd)


def heartbeat_state_if_any(root: Path) -> dict[str, Any] | None:
    try:
        return json.loads((root / HEARTBEAT_STATE_FILE).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def heartbeat_not_running_line(root: Path) -> str | None:
    """The restart-on-next-mail-check line: with a policy configured and no lock held,
    every mail check names the command that brings the heartbeat back (REQ-MAILBOX-19)."""
    if not heartbeat_policy_path(root).is_file():
        return None
    if heartbeat_lock_holder(root) is not None:
        return None
    return f"heartbeat configured but not running: run {root / 'bin' / 'mailbox'} heartbeat start"


heartbeat_app = typer.Typer(no_args_is_help=True, add_completion=False)
app.add_typer(heartbeat_app, name="heartbeat")


@heartbeat_app.command()
def run(
    once: Annotated[bool, typer.Option("--once", help="Run one catch-up pass and exit")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print each firing instead of acting; write no log")] = False,
) -> None:
    """The heartbeat loop: watch the mesh's members and act on stalls per heartbeat.toml."""
    root = mailbox_root()
    policy = load_heartbeat_policy(root, required=True)
    lock = HeartbeatLock(root).acquire()
    if not isinstance(lock, HeartbeatLock):
        fail(
            f"another heartbeat already holds {root / HEARTBEAT_LOCK_FILE}"
            f" (pid {lock.pid}, pane {lock.pane}, started {lock.started})"
        )
    try:
        loop = HeartbeatLoop(root, policy)
        if once:
            # one pass fires from directly observed evidence: file ages and
            # transcript age; idle and blocked durations are unknown and cannot fire
            loop.catchup(dry_run)
        else:
            loop.run(dry_run)
    finally:
        lock.release()


@heartbeat_app.command()
def start() -> None:
    """Launch `run` in a new herdr tab labelled <mesh>-heartbeat and wait until it holds the lock."""
    root = mailbox_root()
    own_name(root)  # starting the heartbeat is acting in the mesh
    load_heartbeat_policy(root, required=True)
    helper = root / "bin" / "mailbox"
    created = json.loads(herdr(
        "tab", "create", "--workspace", own_workspace(),
        "--label", f"{root.name}-heartbeat", "--no-focus",
    ))["result"]
    tab_id = created["tab"]["tab_id"]
    pane = created["root_pane"]["pane_id"]
    herdr("pane", "run", pane, f"{shlex.quote(str(helper))} heartbeat run")
    deadline = time.monotonic() + START_LOCK_WAIT_S
    while time.monotonic() < deadline:
        holder = heartbeat_lock_holder(root)
        if holder is not None:
            if holder.pane == pane:
                typer.echo(f"heartbeat running in pane {pane} (tab {tab_id})")
                return
            herdr("tab", "close", tab_id)
            fail(
                f"another heartbeat already holds the lock (pid {holder.pid}, pane {holder.pane});"
                " the tab this start opened is closed"
            )
        time.sleep(0.5)
    fail(
        f"the heartbeat did not take the lock within {START_LOCK_WAIT_S:g}s; its tab {tab_id}"
        f" (pane {pane}) is left open - read the pane for the failure"
    )


@heartbeat_app.command()
def stop() -> None:
    """End the running heartbeat loop and close its tab. A holder outside herdr has no tab to close."""
    root = mailbox_root()
    own_name(root)
    holder = heartbeat_lock_holder(root)
    if holder is None:
        typer.echo("heartbeat is not running")
        return
    if holder.pid is not None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(holder.pid, signal.SIGTERM)
    deadline = time.monotonic() + STOP_RELEASE_WAIT_S
    while time.monotonic() < deadline:
        if heartbeat_lock_holder(root) is None:
            break
        time.sleep(STOP_RELEASE_POLL_S)
    if holder.tab is not None:
        herdr("tab", "close", holder.tab)
    typer.echo("heartbeat stopped")


@heartbeat_app.command()
def reload() -> None:
    """Signal the running loop to re-read heartbeat.toml now, instead of at the next pass."""
    root = mailbox_root()
    own_name(root)
    holder = heartbeat_lock_holder(root)
    if holder is None:
        fail("heartbeat is not running")
    if holder.pid is not None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(holder.pid, signal.SIGHUP)
    typer.echo("reload signalled")


@heartbeat_app.command()
def status() -> None:
    """Report the heartbeat: running or not, the holding pane, the connection, the last pass, per-member state. Needs no join."""
    root = mailbox_root()
    if not heartbeat_policy_path(root).is_file():
        typer.echo("heartbeat: no heartbeat.toml - off")
        return
    holder = heartbeat_lock_holder(root)
    if holder is None:
        typer.echo(f"heartbeat: configured but not running - run {root / 'bin' / 'mailbox'} heartbeat start")
    else:
        typer.echo(
            f"heartbeat: running (pid {holder.pid}, pane {holder.pane}, started {holder.started})"
        )
    state = heartbeat_state_if_any(root)
    if state is None:
        return
    typer.echo(f"connected: {state.get('connected')}  last pass: {state.get('last_pass')}")
    for name, watched in sorted((state.get("members") or {}).items()):
        typer.echo(
            f"{name}: status {watched.get('status')}  unread {watched.get('unread')}"
            f"  last fire {json.dumps(watched.get('last_fire'), sort_keys=True)}"
        )


@heartbeat_app.command("init")
def init_heartbeat(
    template: Annotated[str, typer.Option(help="overseer-worker | peers | log-only")],
    overseer: Annotated[str | None, typer.Option(help="overseer-worker only: the overseer member name")] = None,
    worker: Annotated[str | None, typer.Option(help="overseer-worker only: the worker member name")] = None,
) -> None:
    """Write heartbeat.toml from a shipped template. Refuses to overwrite an existing file."""
    root = mailbox_root()
    own_name(root)
    path = heartbeat_policy_path(root)
    if path.is_file():
        fail(f"{path} already exists; heartbeat init refuses to overwrite it")
    roster = members(root)
    if template == "overseer-worker":
        if not overseer or not worker:
            fail("the overseer-worker template takes --overseer <member> and --worker <member>")
        check_members(root, [overseer, worker])
        text = overseer_worker_template(overseer, worker)
    elif template == "peers":
        if not roster:
            fail("the mesh has no members to watch")
        text = peers_template(roster)
    elif template == "log-only":
        if not roster:
            fail("the mesh has no members to watch")
        text = log_only_template(roster)
    else:
        fail(f"unknown template {template!r}; shipped templates: overseer-worker, peers, log-only")
    # a template is shipped only in a shape its own validation accepts
    policy, problems = parse_policy(text, path, {m.name: m for m in roster})
    if policy is None:
        fail(f"the {template} template failed its own validation: {problems}")
    write_atomic(path, text)
    typer.echo(f"wrote {path} ({len(policy.rules)} members watched); start it with {root / 'bin' / 'mailbox'} heartbeat start")


def audit_members(root: Path) -> None:
    # lenient by design: this is the recovery path for exactly the member files
    # the loud roster verbs refuse (every verb routes through read_member)
    flagged = False
    for path in sorted((root / "members").iterdir()):
        fields = {key: value for key, _, value in (line.partition("=") for line in path.read_text().splitlines())}
        problem = member_file_problem(fields)
        if problem is None and "pane" not in fields:
            problem = "no seat lines (pre-seat-line join or a retired name)"
        if problem is None:
            continue
        flagged = True
        # the role is peer-controlled free text: quote it so a crafted role cannot
        # escape the printed command when the user pastes it
        role = shlex.quote(fields.get("role") or "<role>")
        typer.echo(
            f"{path.name}: {problem} - re-join if alive: run {root / 'bin' / 'mailbox'} join {path.name} "
            f"--role {role}; if retired, delete {path} (the session running update deletes it on your confirmation)"
        )
    if not flagged:
        typer.echo("member audit: every member file carries seat lines and a role")


@app.command()
def update(mesh_path: Annotated[Path, typer.Argument(help="The mesh to bring current with this skill source")]) -> None:
    """Migrate a mesh's helper and README, then audit its members. Run from the skill, not the mesh."""
    if not TEMPLATE.is_file():
        fail(f"{TEMPLATE} is missing - run update from the skill source, not from a mesh's bin/ copy")
    root = mesh_path.resolve()
    missing: list[str] = []
    if not (root / "README.md").is_file():
        missing.append(str(root / "README.md"))
    for sub in ("members", "inboxes"):
        if not (root / sub).is_dir():
            missing.append(str(root / sub))
    if not (root / "bin" / "mailbox").is_file():
        missing.append(str(root / "bin" / "mailbox"))
    if missing:
        fail(f"{root} is not an initialised mailbox - missing: {missing}; refusing to touch it")
    skill_script = Path(__file__).resolve()
    # text-parse both sides; the mesh copy is by design possibly foreign bytes - never import it
    mesh_version = read_version(root / "bin" / "mailbox")  # None = pre-stamp
    skill_version = read_version(skill_script)
    if skill_version is None:
        fail(f"{skill_script} carries no MAILBOX_VERSION line; update this agent-config checkout instead of guessing what is stale")
    if mesh_version is not None and mesh_version > skill_version:
        fail(
            f"mesh runs {format_version(mesh_version)}, newer than this skill's {format_version(skill_version)}; "
            "update the agent-config checkout running this session instead - refusing to downgrade the mesh"
        )
    changed: list[str] = []
    if mesh_version != skill_version:
        helper = root / "bin" / "mailbox"
        tmp = helper.with_name(f".{helper.name}.tmp")
        tmp.write_text(skill_script.read_text())
        os.chmod(tmp, 0o755)  # members run bin/mailbox directly; a default-mode copy breaks every command
        os.replace(tmp, helper)
        changed.append("helper")
        typer.echo(f"helper: {format_version(mesh_version) if mesh_version else 'pre-stamp'} -> {format_version(skill_version)}")
    rendered = TEMPLATE.read_text().replace("{{MAILBOX}}", str(root))
    if (root / "README.md").read_text() != rendered:
        write_atomic(root / "README.md", rendered)
        changed.append("README.md")
        typer.echo("README.md: re-rendered from the current template")
    audit_members(root)
    if not changed:
        typer.echo("mesh is current")
        return
    log_event(root, event="update", from_version=None if mesh_version is None else format_version(mesh_version),
              to_version=format_version(skill_version), changed=changed)


if __name__ == "__main__":
    app()
