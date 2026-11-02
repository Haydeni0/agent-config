#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["typer>=0.12"]
# ///
"""Guarded writer for work-package markers and the state line (D4).

The agent owns the judgment (verdict, target state); this tool owns the
write. Fail-closed: every refusal exits nonzero naming what it saw (actual
state, offending marker, unknown value) and writes nothing - a composed
invocation validates everything first and never applies partially.

Usage:
  advance.py <package-dir> --review pass|fail --artifact spec|plan
  advance.py <package-dir> --expect-state <s> --set-state <t>
  advance.py <package-dir> --implemented
Flags compose (--review with the state pair; --implemented with either).
"""
import importlib.util
import re
from pathlib import Path
from typing import Annotated

import typer

REVIEWED_RE = re.compile(r"^Reviewed: (pass|fail) ([1-9]\d*)$")
IMPLEMENTED_RE = re.compile(r"^Implemented$")
STATE_RE = re.compile(r"^state: ([a-z0-9-]+)$")

CHAIN_PAIRS = [
    ("grill", "test-plan"),
    ("test-plan", "spec"),
    ("spec", "plan"),
    ("plan", "implement"),
    ("implement", "code-review"),
    ("code-review", "verify-fix"),
    ("verify-fix", "complete"),
]


class Refused(Exception):
    """A fail-closed refusal; the CLI prints the reason and exits 1."""


def _all_states() -> set[str]:
    """The package state enum from `scripts/package_states.py` - the single
    source; this skill dir ships inside the checkout it belongs to."""
    path = Path(__file__).resolve().parent.parent.parent / "scripts" / "package_states.py"
    if not path.is_file():
        raise Refused(f"cannot locate the state enum at {path}")
    spec = importlib.util.spec_from_file_location("package_states", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ALL_STATES


def _unfenced_nonempty(text: str) -> list[str]:
    out = []
    in_fence = False
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence and s:
            out.append(s)
    return out


def _footer_rounds(text: str, rel: str, is_plan: bool) -> int:
    """Validate the Reviewed footer exactly as check-packages.py does - the
    maximal suffix of unfenced non-empty lines, where `Reviewed: (pass|fail)
    <n>` and, for plan.md, `Implemented` are the markers - and return the
    round count. A malformed marker, a well-formed marker outside the
    suffix, or content after the marker block is a hard error naming the
    line; a gap or duplicate in 1..k is a hard error naming the marker.
    `Implemented` is tolerated in the suffix and never counted as a round."""
    nonempty = _unfenced_nonempty(text)
    marker_idx = {
        i for i, l in enumerate(nonempty)
        if REVIEWED_RE.match(l) or (is_plan and IMPLEMENTED_RE.match(l))
    }
    for l in nonempty:
        if l.startswith("Reviewed:") and not REVIEWED_RE.match(l):
            raise Refused(
                f"{rel}: malformed Reviewed marker: {l!r} (expected 'Reviewed: pass|fail <n>', n >= 1)"
            )
    if marker_idx:
        block_start = min(marker_idx)
        for i in range(block_start, len(nonempty)):
            if i not in marker_idx:
                raise Refused(
                    f"{rel}: {nonempty[block_start][:30]!r} must be a footer line - "
                    f"content after marker block: {nonempty[i][:40]!r}"
                )
    rounds = [(int(m.group(2)), l) for l in nonempty if (m := REVIEWED_RE.match(l))]
    for expected, (n, l) in enumerate(rounds, start=1):
        if n != expected:
            raise Refused(
                f"{rel}: round continuity broken at {l!r} "
                f"(expected round {expected}) - never auto-repaired"
            )
    return len(rounds)


def _review_write(pkg: Path, verdict: str, artifact: str) -> tuple[Path, str, str]:
    """Validate a review-marker append and return (path, rel, marker)."""
    if artifact not in ("spec", "plan"):
        raise Refused(f"unknown artifact {artifact!r} (expected 'spec' or 'plan')")
    if verdict not in ("pass", "fail"):
        raise Refused(f"unknown verdict {verdict!r} (expected 'pass' or 'fail')")
    path = pkg / f"{artifact}.md"
    if not path.exists():
        raise Refused(f"{artifact}.md does not exist in {pkg}")
    k = _footer_rounds(path.read_text(), f"{artifact}.md", is_plan=(artifact == "plan"))
    return path, f"{artifact}.md", f"Reviewed: {verdict} {k + 1 if k else 1}"


def _state_of(decisions_text: str) -> str | None:
    lines = decisions_text.split("\n")
    first = lines[0].rstrip() if lines else ""
    m = STATE_RE.match(first)
    if m:
        return m.group(1)
    if first.strip().lower().startswith("state:"):
        raise Refused(f"decisions.md: malformed state line: {first[:40]!r} (expected 'state: <value>')")
    return None


def _state_write(pkg: Path, expect: str, set_to: str) -> tuple[Path, str]:
    """Validate a state-line rewrite and return (path, new_text)."""
    all_states = _all_states()
    for name, value in (("expect-state", expect), ("set-state", set_to)):
        if value not in all_states:
            raise Refused(f"--{name} names unknown state {value!r}")
    if (expect, set_to) not in CHAIN_PAIRS:
        raise Refused(
            f"invalid transition {expect} -> {set_to} "
            f"(allowed dev-cycle pairs: {', '.join(f'{a} -> {b}' for a, b in CHAIN_PAIRS)})"
        )
    path = pkg / "decisions.md"
    if not path.exists():
        raise Refused(f"decisions.md does not exist in {pkg}")
    text = path.read_text()
    actual = _state_of(text)
    if actual != expect:
        shown = actual if actual is not None else "<none>"
        raise Refused(f"decisions.md: state is {shown!r}, expected {expect!r} - no write")
    lines = text.split("\n")
    lines[0] = f"state: {set_to}"
    return path, "\n".join(lines)


def _implemented_write(pkg: Path) -> tuple[Path, str, str]:
    """Validate an Implemented append and return (path, rel, marker)."""
    path = pkg / "plan.md"
    if not path.exists():
        raise Refused(f"plan.md does not exist in {pkg}")
    if any(IMPLEMENTED_RE.match(l) for l in _unfenced_nonempty(path.read_text())):
        raise Refused("plan.md: an Implemented marker already exists - never duplicated")
    return path, "plan.md", "Implemented"


app = typer.Typer()


@app.command()
def main(
    package_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False,
                                                help="Package directory to write")],
    review: Annotated[str | None, typer.Option("--review",
                                               help="verdict to record: pass or fail")] = None,
    artifact: Annotated[str | None, typer.Option("--artifact",
                                                 help="artifact the verdict belongs to: spec or plan")] = None,
    expect_state: Annotated[str | None, typer.Option("--expect-state",
                                                     help="state the package must currently sit at")] = None,
    set_state: Annotated[str | None, typer.Option("--set-state",
                                                  help="state to write on an exact expect-match")] = None,
    implemented: Annotated[bool, typer.Option("--implemented",
                                              help="append the plan.md Implemented marker")] = False,
) -> None:
    """Guarded review-marker and state-line writes for one package."""
    try:
        if (review is None) != (artifact is None):
            raise Refused("--review and --artifact are required together")
        if (expect_state is None) != (set_state is None):
            raise Refused("--expect-state and --set-state are required together")
        if review is None and expect_state is None and not implemented:
            raise Refused("nothing requested - need --review/--artifact, the state pair, or --implemented")
        # validate everything before any write
        appends: list[tuple[Path, str, str]] = []
        if review is not None:
            appends.append(_review_write(package_dir, review, artifact))
        if implemented:
            appends.append(_implemented_write(package_dir))
        state = _state_write(package_dir, expect_state, set_state) if expect_state is not None else None
        # apply
        for path, rel, marker in appends:
            text = path.read_text()
            path.write_text(text.rstrip("\n") + "\n" + marker + "\n")
        if state is not None:
            state[0].write_text(state[1])
    except Refused as exc:
        print(f"refused: {exc}")
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
