#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["typer>=0.12"]
# ///
"""Backlog lifecycle writer: flock-serialized add/close for the backlog file.

The path is always the first argument - the skill's prose decides the file
(legacy-file resolution and reconcile-when-both stay there). Fail-closed: a
refusal exits nonzero naming what was seen; nothing auto-repairs, renumbers,
or guesses.

Usage:
  backlog.py <file> add "<text>"
  backlog.py <file> close <id> "<record>"
"""
import fcntl
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Annotated

import typer

ITEM_RE = re.compile(r"^- #(\d+) \[", re.M)
HEADING_RE = re.compile(r"^## (.+?)\s*$")
CANONICAL = (
    "# Backlog\n\n"
    "Deferred items for this project. Surfaced when starting work here; picked up on request.\n\n"
    "## Open\n\n"
    "## Done\n"
)


class Refused(Exception):
    """A fail-closed refusal; the CLI prints the reason and exits 1."""


def _lock(path: Path):
    """Exclusive flock on a sibling lock file - never the target itself, so
    the temp+rename swap cannot orphan another process's lock. The lock file
    is never deleted and shows as untracked alongside the backlog - intended,
    same as the backlog itself."""
    lock = path.with_suffix(path.suffix + ".lock")
    fh = open(lock, "a+")
    fcntl.flock(fh, fcntl.LOCK_EX)
    return fh


def _fenced_mask(lines: list[str]) -> list[bool]:
    # True = inside a fence. Fenced lines are invisible to ID, heading, and
    # section scans - a fenced example item is not an item, and a fenced
    # heading does not open a section (matching lint.py's discipline).
    mask = []
    in_fence = False
    for l in lines:
        if l.strip().startswith("```"):
            mask.append(True)
            in_fence = not in_fence
            continue
        mask.append(in_fence)
    return mask


def _require_balanced_fences(lines: list[str]) -> None:
    # An unclosed fence hides everything after it from the scans; refuse
    # rather than allocate IDs or move blocks around a broken region.
    if sum(1 for l in lines if l.strip().startswith("```")) % 2 == 1:
        raise Refused("unclosed code fence - fix the fence before editing")


def _ids(text: str) -> list[int]:
    lines = text.split("\n")
    mask = _fenced_mask(lines)
    out = []
    for l, fenced in zip(lines, mask):
        if not fenced:
            m = ITEM_RE.match(l)
            if m:
                out.append(int(m.group(1)))
    return out


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def _heading_of(lines: list[str], i: int, mask: list[bool] | None = None) -> str | None:
    """Name of the last `## ` heading above line i; None before any heading.
    Fenced heading lines are not headings."""
    name = None
    for k, l in enumerate(lines[:i]):
        if mask is not None and mask[k]:
            continue
        m = HEADING_RE.match(l)
        if m:
            name = m.group(1)
    return name


def add_item(path: Path, text: str) -> None:
    lock = _lock(path)
    try:
        if not path.exists():
            path.write_text(CANONICAL)
        raw = path.read_text()
        lines = raw.split("\n")
        _require_balanced_fences(lines)
        mask = _fenced_mask(lines)
        heading = next((i for i, l in enumerate(lines) if not mask[i] and re.match(r"^## Open\s*$", l)), None)
        if heading is None:
            raise Refused("no ## Open marker")
        ids = _ids(raw)
        nid = (max(ids) + 1) if ids else 1
        if nid in ids:
            raise Refused(f"next id #{nid} already taken")
        line = f"- #{nid} [{date.today():%Y-%m-%d}] {text}"
        insert_at = heading + 2 if heading + 1 < len(lines) and lines[heading + 1] == "" else heading + 1
        lines.insert(insert_at, line)
        _atomic_write(path, "\n".join(lines))
    finally:
        lock.close()


def close_item(path: Path, item_id: int, record: str) -> None:
    lock = _lock(path)
    try:
        raw = path.read_text()
        lines = raw.split("\n")
        _require_balanced_fences(lines)
        mask = _fenced_mask(lines)
        bullet = re.compile(rf"^- #{item_id} \[")
        hits = [i for i, l in enumerate(lines) if not mask[i] and bullet.match(l)]
        if not hits:
            raise Refused(f"no item #{item_id}")
        if len(hits) > 1:
            raise Refused(f"{len(hits)} items #{item_id} - ambiguous")
        i = hits[0]
        heading = _heading_of(lines, i, mask)
        if heading != "Open":
            raise Refused(f"item #{item_id} sits under {heading!r}, not '## Open'")
        # The item block runs to the next column-0 `- ` bullet or `#` heading,
        # or the end of the line list - NEVER a blank line (real items carry
        # blank lines inside their blocks) and never a per-line \Z match
        # (it would match every empty line and truncate the block).
        j = i + 1
        while j < len(lines) and not re.match(r"^(?:- |#)", lines[j]):
            j += 1
        block = lines[i:j]
        # strip trailing blank lines so the record sits adjacent to the
        # item's last content line
        while block and block[-1] == "":
            block.pop()
        block.append(f"  -> DONE {date.today():%Y-%m-%d}: {record}")
        del lines[i:j]
        done_idx = next((k for k, l in enumerate(lines) if not mask[k] and re.match(r"^## Done\s*$", l)), None)
        if done_idx is None:
            open_idx = next((k for k, l in enumerate(lines) if not mask[k] and re.match(r"^## Open\s*$", l)), None)
            if open_idx is None:
                raise Refused("no ## Open marker")
            end = next((k for k in range(open_idx + 1, len(lines)) if not mask[k] and re.match(r"^## ", lines[k])), len(lines))
            lines[end:end] = ["## Done", ""] + block
        else:
            end = next((k for k in range(done_idx + 1, len(lines)) if not mask[k] and re.match(r"^## ", lines[k])), len(lines))
            if end == len(lines) and lines and lines[-1] == "":
                end -= 1  # keep the file's trailing newline element last
            lines[end:end] = block
        _atomic_write(path, "\n".join(lines))
    finally:
        lock.close()


def _run(fn, *args) -> None:
    try:
        fn(*args)
    except Refused as exc:
        print(f"refused: {exc}")
        raise typer.Exit(1) from None


app = typer.Typer()


@app.callback()
def _main(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(help="Backlog file; the skill resolves the path")],
) -> None:
    """Serialized add/close for the backlog file."""
    ctx.obj = file


@app.command()
def add(
    ctx: typer.Context,
    text: Annotated[str, typer.Argument(help="Item text")],
) -> None:
    """Allocate the next ID and insert under ## Open."""
    _run(add_item, ctx.obj, text)


@app.command()
def close(
    ctx: typer.Context,
    id: Annotated[int, typer.Argument(help="Item ID to close")],
    record: Annotated[str, typer.Argument(help="Done-record text")],
) -> None:
    """Record the done line and move the item under ## Done."""
    _run(close_item, ctx.obj, id, record)


if __name__ == "__main__":
    app()
