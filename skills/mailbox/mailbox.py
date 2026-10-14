#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12"]
# ///
"""File mailbox linking running agent sessions in herdr panes.

Layout under the mailbox root: README.md (the contract), bin/mailbox (this
script, copied by `init`), members/<name> (`role=`, plus the `pane=` and
`session=` seat the member joined from), inboxes/<name>/ (unread files) and
inboxes/<name>/handled/ (acted-on files). A member's name is its herdr agent
name. Requests are `<from>.<seq>-<slug>.msg`; a reply reuses the request id
as `<from>.<id>.reply`.
"""

import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

import typer

# `.` separates filename fields, so names and slugs must never contain one
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ID_RE = re.compile(r"^\d{3,}-[a-z0-9]+(-[a-z0-9]+)*$")
# `<from>.<seq>-<slug>.<kind>`; groups mirror NAME_RE
MESSAGE_RE = re.compile(
    r"^(?P<sender>[a-z0-9]+(?:-[a-z0-9]+)*)\.(?P<seq>\d+)-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.(?P<kind>msg|reply)$"
)
NO_MAIL = "no unread mail"
# zero-padded so `ls` lists one sender's requests in send order
SEQ_WIDTH = 3
# long enough to catch a turn that is finishing, short enough not to stall the
# sender's own turn; a claude recipient still busy past this is prompted
# mid-turn anyway (see ring)
RING_WAIT_MS = 30_000
TEMPLATE = Path(__file__).resolve().parent / "README.template.md"

app = typer.Typer(no_args_is_help=True, add_completion=False)


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


def live_pane(name: str) -> str | None:
    """Pane of the live herdr agent called `name`, or None when no agent has it."""
    try:
        output = herdr("agent", "get", name)
    except HerdrError as exc:
        if exc.code == "agent_not_found":
            return None
        raise
    return json.loads(output)["result"]["agent"]["pane_id"]


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


def read_member(path: Path) -> Member:
    fields = {key: value for key, _, value in (line.partition("=") for line in path.read_text().splitlines())}
    seat = Seat(pane=fields["pane"], session=fields["session"]) if "pane" in fields else None
    return Member(name=path.name, role=fields["role"], seat=seat)


def write_member(root: Path, member: Member) -> None:
    lines = [f"role={member.role}"]
    if member.seat is not None:
        lines += [f"pane={member.seat.pane}", f"session={member.seat.session}"]
    (root / "members" / member.name).write_text("\n".join(lines) + "\n")


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


@app.command()
def init(directory: Path) -> None:
    """Create a mailbox at DIRECTORY and install this helper as its bin/mailbox."""
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
    seat = own_seat()
    holder = live_pane(name)
    if holder is not None and holder != seat.pane:
        fail(f"name {name!r} is held by the herdr agent in pane {holder}; pick another name")
    herdr("agent", "rename", seat.pane, name)
    (root / "inboxes" / name / "handled").mkdir(parents=True, exist_ok=True)
    for other in members(root):
        # a re-join under a new name must not leave the old name claiming this seat
        if other.name != name and other.seat == seat:
            write_member(root, replace(other, seat=None))
    write_member(root, Member(name=name, role=role, seat=seat))
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

    Strict (inbox, take): a foreign file is a loud failure. Lenient (status):
    one member's stray file must not hide every member's counts."""
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


# herdr error codes that mean "leave the file for the receiver's own inbox check"
UNRUNG = {
    "timeout": RingOutcome.NOT_IDLE,
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


def verified_own_name(root: Path) -> str:
    """own_name, cross-checked against herdr: a herdr restart reuses pane ids, so a seat can outlive its session."""
    name = own_name(root)
    pane = own_pane()
    live = live_pane(name)
    if live != pane:
        fail(
            f"member file {name!r} claims pane {pane}, but the live herdr agent {name!r} is in "
            f"{live or 'no pane'} - a stale claim; re-join with {root / 'bin' / 'mailbox'} join <name> --role <role> "
            "before taking mail"
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
    pattern = re.compile(rf"^{re.escape(sender)}\.(\d+)-")
    seqs = (int(m.group(1)) for p in root.glob("inboxes/*/**/*.msg") if (m := pattern.match(p.name)))
    return max(seqs, default=0) + 1


def write_atomic(path: Path, body: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(body)
    os.replace(tmp, path)


def write_messages(root: Path, sender: str, msg_id: str, kind: Kind, body: str, recipients: list[str]) -> dict[str, Path]:
    paths = {name: root / "inboxes" / name / f"{sender}.{msg_id}.{kind}" for name in recipients}
    taken = [str(p) for p in paths.values() if p.exists() or (p.parent / "handled" / p.name).exists()]
    if taken:
        fail(f"refusing to overwrite existing message files: {taken}")
    for path in paths.values():
        write_atomic(path, body)
    return paths


def wake_line(root: Path, name: str) -> str:
    return f": mail waiting in {root}/inboxes/{name}/ - follow {root}/README.md"


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
    msg_id = f"{next_seq(root, sender):0{SEQ_WIDTH}d}-{slug}"
    deliver(root, sender, msg_id, Kind.MSG, to, ring_now)


@app.command()
def reply(msg_id: Annotated[str, typer.Argument(metavar="ID")], to: str, ring_now: RingFlag = True) -> None:
    """Reply (body on stdin) to request ID from member TO."""
    root = mailbox_root()
    if not ID_RE.fullmatch(msg_id):
        fail(f"id {msg_id!r} must look like 007-review-api (<seq>-<slug> from the request filename)")
    check_members(root, [to])
    sender = own_name(root)
    deliver(root, sender, msg_id, Kind.REPLY, [to], ring_now)


@app.command()
def inbox() -> None:
    """List your unread mail without taking it."""
    root = mailbox_root()
    unread = messages_in(root / "inboxes" / own_name(root))
    if not unread:
        typer.echo(NO_MAIL)
        return
    for message in unread:
        typer.echo(describe(message))


@app.command()
def take() -> None:
    """Print all unread mail, then mark exactly what was printed handled."""
    root = mailbox_root()
    box = root / "inboxes" / verified_own_name(root)
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


if __name__ == "__main__":
    app()
