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
(acted-on files) and log.jsonl (the append-only trace of sends, replies and
takes). A member's name is its herdr agent name. Requests are
`<from>.<seq>-<slug>.msg`; a reply reuses the request id as
`<from>.<id>.reply`.
"""

import contextlib
import json
import os
import re
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
MAILBOX_VERSION = "2026-10-15.01"
VERSION_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\.(?P<rev>\d{2})$")
Version = tuple[str, int]


def parse_version(text: str, path: Path) -> Version:
    match = VERSION_RE.fullmatch(text)
    if match is None:
        fail(f"{path} carries MAILBOX_VERSION {text!r}, which is not `YYYY-MM-DD.NN`; refusing to order it")
    return match["date"], int(match["rev"])


def read_version(script: Path) -> Version | None:
    """The version a helper copy carries, text-parsed (never imported); None = pre-stamp."""
    for line in script.read_text().splitlines():
        if line.startswith("MAILBOX_VERSION ="):
            return parse_version(line.partition('"')[2].rpartition('"')[0], script)
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


def read_member(path: Path) -> Member:
    fields = {key: value for key, _, value in (line.partition("=") for line in path.read_text().splitlines())}
    if "role" not in fields:
        fail(f"member file {path} has no role= line; fix it or delete the file and re-join")
    if "pane" in fields and "session" not in fields:
        fail(f"member file {path} claims pane= without session=; fix it or delete the file and re-join")
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
    """Join the mesh as NAME: rename this pane's herdr agent, write the member file, create the inbox."""
    root = mailbox_root()
    check_token(name, "name")
    if "\n" in role or "\r" in role:
        fail("role must be a single line - it becomes a line in the member file")
    seat = own_seat()
    holder = live_pane(name)
    if holder is not None and holder != seat.pane:
        fail(f"name {name!r} is held by the herdr agent in pane {holder}; pick another name")
    herdr("agent", "rename", seat.pane, name)
    record = agent_record(name)
    (root / "inboxes" / name / "handled").mkdir(parents=True, exist_ok=True)
    for other in members(root):
        # a re-join under a new name must not leave the old name claiming this seat
        if other.name != name and other.seat == seat:
            write_member(root, replace(other, seat=None))
    write_member(
        root,
        Member(
            name=name,
            role=role,
            seat=seat,
            harness=record.get("agent"),
            harness_session=(record.get("agent_session") or {}).get("value"),
        ),
    )
    typer.echo(f"joined as {name}; your inbox is {root / 'inboxes' / name}; follow {root / 'README.md'}")


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
    OFFLINE = "not rung: no live herdr agent with this name - tell the user; a session joining under it drains the inbox"


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
    """own_name, cross-checked against herdr: pane ids repeat, so a recorded seat can outlive its agent."""
    name = own_name(root)
    member = member_named(root, name)
    record = agent_record(name)
    rejoin = f"re-join with {root / 'bin' / 'mailbox'} join <name> --role <role> before taking mail"
    live_session = (record.get("agent_session") or {}).get("value")
    if member is not None and member.harness_session is not None:
        # the harness session is the durable anchor: a reused pane always runs a new session
        if live_session != member.harness_session:
            fail(
                f"member file {name!r} records harness session {member.harness_session}, but the live "
                f"herdr agent {name!r} is {live_session or 'sessionless'} - a stale claim; {rejoin}"
            )
        return name
    pane = record.get("pane_id")
    if pane != own_pane():
        fail(
            f"member file {name!r} claims pane {own_pane()}, but the live herdr agent {name!r} is in "
            f"{pane or 'no pane'} - a stale claim; {rejoin}"
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


def recipient_harness(name: str) -> str:
    """Harness of the live herdr agent called `name`, e.g. `claude`."""
    return json.loads(herdr("agent", "get", name))["result"]["agent"]["agent"]


def ring(root: Path, name: str) -> RingOutcome:
    busy = False
    try:
        herdr("agent", "wait", name, "--until", "idle", "--until", "done", "--timeout", str(RING_WAIT_MS))
    except HerdrError as exc:
        if exc.code == "timeout":
            # a busy recipient may not end its turn for hours (an orchestrator
            # waiting on subagents), and its turn-end inbox check is not
            # reliable (#37); a claude agent takes a mid-turn prompt fine - the
            # line queues in its input - so prompt anyway, and herdr still
            # refuses to prompt a blocked agent. Other harnesses are unprobed.
            if recipient_harness(name) != "claude":
                return RingOutcome.NOT_IDLE
            busy = True
        elif exc.code in UNRUNG:
            return UNRUNG[exc.code]
        else:
            raise
    try:
        herdr("agent", "prompt", name, wake_line(root, name))
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


if __name__ == "__main__":
    app()
