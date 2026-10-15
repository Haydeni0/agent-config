#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12"]
# ///
"""File mailbox linking running agent sessions in herdr panes.

Layout under the mailbox root: README.md (the contract), bin/mailbox (this
script, copied by `init`), members/<name> (`role=`, plus the seat the member
joined from - `pane=`, `session=`, `harness=`, `harness-session=` - as herdr
reports them), inboxes/<name>/ (unread files), inboxes/<name>/handled/
(acted-on files) and log.jsonl (the append-only trace of joins, sends, replies
and takes). A member's name is mesh-local, not its herdr agent name: identity
is the recorded seat pane plus the harness session, so one pane may hold
different names in different meshes. Requests are
`<from>.<seq>-<slug>.msg`; a reply reuses the request id as
`<from>.<id>.reply`.
"""

import contextlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
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
# `<from>.<seq>-<slug>.<kind>`; groups mirror NAME_RE
MESSAGE_RE = re.compile(
    r"^(?P<sender>[a-z0-9]+(?:-[a-z0-9]+)*)\.(?P<seq>\d+)-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.(?P<kind>msg|reply)$"
)
NO_MAIL = "no unread mail"
# zero-padded so `ls` lists one sender's requests in send order (invariant
# holds below 1000 sends per sender - `"1000-"` sorts before `"999-"`)
SEQ_WIDTH = 3
# long enough to catch a turn that is finishing, short enough not to stall the
# sender's own turn; a claude recipient still busy past this is prompted
# mid-turn anyway (see ring)
RING_WAIT_MS = 30_000
TEMPLATE = Path(__file__).resolve().parent / "README.template.md"

# The helper's version. `YYYY-MM-DD.NN`, revision zero-padded; comparison parses
# (date, revision) tuples, never strings. Bump the revision in the same commit
# as any behavior change - a forgotten bump makes `update` report a changed
# helper as current (the accepted residual, D8).
MAILBOX_VERSION = "2026-10-15.06"
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
    )


def write_member(root: Path, member: Member) -> None:
    lines = [f"role={member.role}"]
    if member.seat is not None:
        lines += [f"pane={member.seat.pane}", f"session={member.seat.session}"]
    if member.harness is not None:
        lines.append(f"harness={member.harness}")
    if member.harness_session is not None:
        lines.append(f"harness-session={member.harness_session}")
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
    # join of its day renamed the pane to the member name, so the name is the
    # only anchor that can still be checked
    record = agent_record(member.name)
    if record.get("pane_id") != member.seat.pane:
        return False, None
    return True, (record.get("agent_session") or {}).get("value")


def mailbox_root() -> Path:
    root = Path(__file__).resolve().parent.parent
    if not (root / "README.md").is_file() or not (root / "members").is_dir():
        fail(
            f"{root} is not an initialised mailbox; call this script as <mailbox>/bin/mailbox "
            "(create a mailbox with `mailbox.py init <dir>` from the mailbox skill)"
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
def join(name: str, role: Annotated[str, typer.Option(help="Free text, e.g. planner")]) -> None:
    """Join the mesh as NAME: write the member file, create the inbox, name this pane's herdr agent when it has none."""
    root = mailbox_root()
    check_token(name, "name")
    if "\n" in role or "\r" in role:
        fail("role must be a single line - it becomes a line in the member file")
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


class RingOutcome(StrEnum):
    RUNG = "rung"
    BUSY = "rung while busy: recipient was mid-turn; the line queues in its input until it reads it"
    NOT_IDLE = f"not rung: not idle within {RING_WAIT_MS // 1000} s and mid-turn prompting is unverified for its harness; the file waits in its inbox"
    BLOCKED = "not rung: at a permission prompt; the file waits in its inbox"
    OFFLINE = "not rung: no live herdr agent at the member's seat - tell the user; a session joining under it drains the inbox"


# herdr error codes that mean "leave the file for the receiver's own inbox check".
# `timeout` is not here: it means different things per verb (a busy recipient on
# wait, a slow prompt on prompt) and is handled where it can be attributed.
UNRUNG = {
    "agent_blocked": RingOutcome.BLOCKED,
    "agent_not_found": RingOutcome.OFFLINE,
}

RingFlag = Annotated[bool, typer.Option("--ring/--no-ring", help="Wake the recipient now; --no-ring for non-urgent mail")]


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
    taken = [str(p) for p in paths.values() if p.exists() or (p.parent / "handled" / p.name).exists()]
    if taken:
        hint = f"; {ONE_REPLY_PER_REQUEST}" if kind is Kind.REPLY else ""
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


def ring(root: Path, name: str) -> RingOutcome:
    # the herdr name is not the member's identity (one pane, several meshes,
    # several names): ring the member's seat pane, and only while its recorded
    # claim is live - never a bare name
    member = member_named(root, name)
    if member is None or not live_claim(member)[0]:
        return RingOutcome.OFFLINE
    pane = member.seat.pane
    busy = False
    try:
        herdr("agent", "wait", pane, "--until", "idle", "--until", "done", "--timeout", str(RING_WAIT_MS))
    except HerdrError as exc:
        if exc.code == "timeout":
            # a busy recipient may not end its turn for hours (an orchestrator
            # waiting on subagents), and its turn-end inbox check is not
            # reliable (#37); a claude agent takes a mid-turn prompt fine - the
            # line queues in its input - so prompt anyway, and herdr still
            # refuses to prompt a blocked agent. Other harnesses are unprobed.
            if recipient_harness(pane) != "claude":
                return RingOutcome.NOT_IDLE
            busy = True
        elif exc.code in UNRUNG:
            return UNRUNG[exc.code]
        else:
            raise
    try:
        herdr("agent", "prompt", pane, wake_line(root, name))
    except HerdrError as exc:
        if exc.code in UNRUNG:
            return UNRUNG[exc.code]
        raise
    return RingOutcome.BUSY if busy else RingOutcome.RUNG


def ring_all(root: Path, paths: dict[str, Path]) -> None:
    failed = False
    for name, path in paths.items():
        try:
            outcome = ring(root, name)
        except HerdrError as exc:
            typer.echo(f"{path} written, ring failed: {exc}")
            failed = True
            continue
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


@app.command()
def send(slug: str, to: list[str], ring_now: RingFlag = True) -> None:
    """Send a new request (body on stdin) to one or more members."""
    root = mailbox_root()
    check_token(slug, "slug")
    check_members(root, to)
    sender = own_name(root)
    seq = f"{next_seq(root, sender):0{SEQ_WIDTH}d}"
    # agents often prefix the slug with the seq they expect; the helper adds it
    msg_id = f"{seq}-{slug.removeprefix(f'{seq}-')}"
    deliver(root, sender, msg_id, Kind.MSG, to, ring_now)


def resolve_request(root: Path, me: str, ref: str, sender: str) -> Message:
    """The request REF from SENDER, unread or handled, in ME's inbox."""
    match = REQUEST_REF_RE.fullmatch(Path(ref).name)
    if match is None:
        fail(f"id {ref!r} must be the request's seq (7), id (007-review-api) or filename")
    seq, slug = int(match["seq"]), match["slug"]
    box = root / "inboxes" / me
    # requests only: a `.reply` carries the replier's name with *your* seq, so it can share <sender, seq> with one
    requests = [m for d in (box, box / "handled") for m in messages_in(d) if m.kind is Kind.MSG]
    same_seq = [m for m in requests if m.seq == seq]
    found = [m for m in same_seq if m.sender == sender and slug in (None, m.slug)]
    if len(found) == 1:
        return found[0]
    if found:
        fail(f"id {ref!r} matches several requests from {sender!r}: {[m.path.name for m in found]}")
    if same_seq:
        listing = ", ".join(f"{m.path.name} (from {m.sender})" for m in same_seq)
        fail(f"no request {ref!r} from {sender!r}; requests with seq {seq}: {listing} - reply to the name before the first '.'")
    from_sender = [m.msg_id for m in requests if m.sender == sender]
    fail(f"no request with seq {seq} in your inbox or handled/; requests from {sender!r}: {from_sender or 'none'}")


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
        fail(f"you are {sender!r}; address the reply to the request's sender - the name before the first '.' in its filename")
    request = resolve_request(root, sender, ref, to)
    deliver(root, sender, request.msg_id, Kind.REPLY, [to], ring_now)


@app.command()
def inbox() -> None:
    """List your unread mail without taking it."""
    root = mailbox_root()
    unread = messages_in(root / "inboxes" / own_name(root))
    if not unread:
        typer.echo(NO_MAIL)
        return
    for message in unread:
        try:
            typer.echo(describe(message))
        except FileNotFoundError:
            continue  # a concurrent take already acked it


@app.command()
def take() -> None:
    """Print all unread mail, then mark exactly what was printed handled."""
    root = mailbox_root()
    name = verified_own_name(root)
    box = root / "inboxes" / name
    printed: list[Message] = []
    for message in messages_in(box):
        try:
            body = message.path.read_text()
        except FileNotFoundError:
            continue  # a concurrent take already acked it
        typer.echo(f"=== {message.path.name}")
        typer.echo(body.rstrip("\n"))
        printed.append(message)
    if not printed:
        typer.echo(NO_MAIL)
        return
    (box / "handled").mkdir(parents=True, exist_ok=True)  # an old-mesh member may lack it
    for message in printed:
        with contextlib.suppress(FileNotFoundError):  # a concurrent take already acked it
            message.path.rename(box / "handled" / message.path.name)
    member = member_named(root, name)
    log_event(root, event="taken", member=name, session=member.harness_session if member else None,
              files=[message.path.name for message in printed])


@app.command()
def status(member: Annotated[str | None, typer.Argument(help="Show only this member's unread ids")] = None) -> None:
    """Every member's role and unread/handled counts, or one member's unread ids. Needs no join."""
    root = mailbox_root()
    if member is not None:
        check_members(root, [member])
        unread = messages_in(root / "inboxes" / member, strict=False)
        if not unread:
            typer.echo(f"{member}: {NO_MAIL}")
        for message in unread:
            typer.echo(describe(message))
        return
    for m in members(root):
        box = root / "inboxes" / m.name
        # lenient: one member's stray file must not hide every member's counts
        typer.echo(f"{m.name}  ({m.role})  unread {len(messages_in(box, strict=False))}  handled {len(messages_in(box / 'handled', strict=False))}")


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
        outcome = ring(root, member)
    except HerdrError as exc:
        fail(f"{member}: ring failed: {exc}")
    typer.echo(f"{member}: {outcome}")


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
