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
            error = json.loads(proc.stdout)["error"]
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
            "(create a mailbox with `mailbox.py init <dir>` from the agent-mailbox skill)"
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


if __name__ == "__main__":
    app()
