#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12"]
# ///
"""File mailbox linking running agent sessions in herdr panes.

Layout under the mailbox root: README.md (the contract), bin/mailbox (this
script, copied by `init`), members/<name> (`role=...`), inboxes/<name>/
(unread files) and inboxes/<name>/handled/ (acted-on files). A member's name
is its herdr agent name. Requests are `<from>.<seq>-<slug>.msg`; a reply
reuses the request id as `<from>.<id>.reply`.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

import typer

# `.` separates filename fields, so names and slugs must never contain one
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ID_RE = re.compile(r"^\d{3,}-[a-z0-9]+(-[a-z0-9]+)*$")
# zero-padded so `ls` lists one sender's requests in send order
SEQ_WIDTH = 3
# long enough to catch a turn that is finishing, short enough not to stall the
# sender's own turn; a receiver still busy picks the file up at its turn end
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
    pane = own_pane()
    holder = live_pane(name)
    if holder is not None and holder != pane:
        fail(f"name {name!r} is held by the herdr agent in pane {holder}; pick another name")
    herdr("agent", "rename", pane, name)
    (root / "inboxes" / name / "handled").mkdir(parents=True, exist_ok=True)
    (root / "members" / name).write_text(f"role={role}\n")
    typer.echo(f"joined as {name}; your inbox is {root / 'inboxes' / name}; follow {root / 'README.md'}")


class Kind(StrEnum):
    MSG = "msg"
    REPLY = "reply"


class RingOutcome(StrEnum):
    RUNG = "rung"
    NOT_IDLE = f"not rung: not idle within {RING_WAIT_MS // 1000} s - its turn-end inbox check will pick it up"
    BLOCKED = "not rung: at a permission prompt - its turn-end inbox check will pick it up"
    OFFLINE = "not rung: no live herdr agent with this name - tell the user; a session joining under it drains the inbox"


# herdr error codes that mean "leave the file for the receiver's own inbox check"
UNRUNG = {
    "timeout": RingOutcome.NOT_IDLE,
    "agent_blocked": RingOutcome.BLOCKED,
    "agent_not_found": RingOutcome.OFFLINE,
}

RingFlag = Annotated[bool, typer.Option("--ring/--no-ring", help="Wake the recipient now; --no-ring for non-urgent mail")]


def own_name(root: Path) -> str:
    pane = own_pane()
    for member in sorted(p.name for p in (root / "members").iterdir()):
        if live_pane(member) == pane:
            return member
    fail(f"pane {pane} is not a joined member; run {root / 'bin' / 'mailbox'} join <name> --role <role> first")


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


def ring(root: Path, name: str) -> RingOutcome:
    try:
        herdr("agent", "wait", name, "--until", "idle", "--until", "done", "--timeout", str(RING_WAIT_MS))
        herdr("agent", "prompt", name, wake_line(root, name))
    except HerdrError as exc:
        if exc.code in UNRUNG:
            return UNRUNG[exc.code]
        raise
    return RingOutcome.RUNG


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


if __name__ == "__main__":
    app()
