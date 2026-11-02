#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["typer>=0.12"]
# ///
"""Canonical-section and disposition writer for package decisions.md.

Fail-closed: every refusal exits nonzero naming what it saw and writes
nothing. `## Review nits` is deliberately absent from the insert map - it is
append-per-round, which an insert-once command cannot serve.

Usage:
  sections.py <package-dir> insert <outcome|deviation-log|review-findings>
  sections.py <package-dir> disposition <n> "<text>"
"""
import re
from pathlib import Path
from typing import Annotated

import typer

STATE_RE = re.compile(r"^state: ([a-z0-9-]+)$")
SECTION_RE = re.compile(r"^## (.+?)\s*$")
FINDING_RE_FMT = r"^(\d+)\. "

CANONICAL = {
    "outcome": "## Outcome",
    "deviation-log": "## Deviation log",
    "review-findings": "## Review findings",
}


class Refused(Exception):
    """A fail-closed refusal; the CLI prints the reason and exits 1."""


def _require_decisions(pkg: Path) -> Path:
    path = pkg / "decisions.md"
    if not path.exists():
        raise Refused(f"decisions.md does not exist in {pkg}")
    return path


def _require_state_line(text: str) -> None:
    first = text.split("\n", 1)[0].rstrip()
    if STATE_RE.match(first):
        return
    if first.strip().lower().startswith("state:"):
        raise Refused(f"decisions.md: malformed state line: {first[:40]!r} (expected 'state: <value>')")
    raise Refused("decisions.md: no state: line 1 - refusing to file into a malformed package")


def _require_balanced_fences(text: str, rel: str) -> None:
    # An unclosed fence would swallow whatever this tool appends, and the
    # fence-blind scan would then never see it - refuse before any write.
    if sum(1 for l in text.splitlines() if l.strip().startswith("```")) % 2 == 1:
        raise Refused(f"{rel}: unclosed code fence - fix the fence before filing")


def _fenced_mask(lines: list[str]) -> list[bool]:
    # True = inside a fence. Fenced lines are invisible to heading/section
    # scans, matching check-packages' unfenced discipline.
    mask = []
    in_fence = False
    for l in lines:
        if l.strip().startswith("```"):
            mask.append(True)
            in_fence = not in_fence
            continue
        mask.append(in_fence)
    return mask


def insert_section(pkg: Path, name: str) -> None:
    if name not in CANONICAL:
        raise Refused(
            f"unknown section {name!r} (insertable: {' | '.join(sorted(CANONICAL))}; "
            "`## Review nits` stays prose - append-per-round)"
        )
    path = _require_decisions(pkg)
    text = path.read_text()
    _require_state_line(text)
    _require_balanced_fences(text, "decisions.md")
    heading = CANONICAL[name]
    base = heading[3:]
    mask = _fenced_mask(text.splitlines())
    for l, fenced in zip(text.splitlines(), mask):
        if not fenced and re.match(rf"^## {re.escape(base)}\s*$", l):
            raise Refused(f"decisions.md: {heading} already exists - never duplicated")
    path.write_text(text.rstrip("\n") + "\n\n" + heading + "\n")


def file_disposition(pkg: Path, finding_num: int, record: str) -> None:
    path = _require_decisions(pkg)
    raw = path.read_text()
    _require_balanced_fences(raw, "decisions.md")
    lines = raw.split("\n")
    mask = _fenced_mask(lines)
    rf = next(
        (i for i, l in enumerate(lines) if not mask[i] and re.match(r"^## Review findings\s*$", l)),
        None,
    )
    if rf is None:
        raise Refused("decisions.md: no ## Review findings section")
    end = next(
        (i for i in range(rf + 1, len(lines)) if not mask[i] and SECTION_RE.match(lines[i])),
        len(lines),
    )
    hits = [
        i for i in range(rf + 1, end)
        if not mask[i] and re.match(rf"^{finding_num}\. ", lines[i])
    ]
    if not hits:
        raise Refused(f"no finding {finding_num} under ## Review findings")
    if len(hits) > 1:
        raise Refused(f"{len(hits)} findings numbered {finding_num} under ## Review findings - ambiguous")
    i = hits[0]
    # the finding's block runs to the next numbered finding or the section
    # end; the disposition sits after its last continuation line
    j = i + 1
    while j < end and (mask[j] or not re.match(FINDING_RE_FMT, lines[j])):
        j += 1
    while j > i and lines[j - 1].strip() == "":
        j -= 1
    lines.insert(j, f"   Disposition: {record}")
    path.write_text("\n".join(lines))


app = typer.Typer()


@app.callback()
def _main(
    ctx: typer.Context,
    package_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False,
                                                help="Package directory to write")],
) -> None:
    """Canonical-section and disposition writer for decisions.md."""
    ctx.obj = package_dir


@app.command()
def insert(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Section to append: outcome | deviation-log | review-findings")],
) -> None:
    """Append one canonical section to decisions.md; an existing heading is
    refused, never duplicated."""
    try:
        insert_section(ctx.obj, name)
    except Refused as exc:
        print(f"refused: {exc}")
        raise typer.Exit(1) from None


@app.command()
def disposition(
    ctx: typer.Context,
    n: Annotated[int, typer.Argument(help="Finding number under ## Review findings")],
    record: Annotated[str, typer.Argument(help="Disposition text (fixed / discarded: reason)")],
) -> None:
    """Append the disposition line after a numbered review finding."""
    try:
        file_disposition(ctx.obj, n, record)
    except Refused as exc:
        print(f"refused: {exc}")
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
