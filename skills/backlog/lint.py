#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Structural lint for the backlog file - the single structural-check home.

Fail-closed: findings one per line, exit 1 on any. The Open/Done rules apply
only to item blocks under the `## Open` and `## Done` headings - items in any
other section (the imported-legacy section) are skipped entirely. A done
record is a `-> DONE` or `-> CLOSED` token anywhere in the item block (the
real file carries both forms, often mid-line on the bullet itself).

Usage:
  lint.py <backlog.md> [--requirements <contract.md>]

With --requirements, bare #N tokens in the contract's pipe-table rows must
resolve to a backlog item ID (union of all item IDs in the file).
"""
import re
import sys
from pathlib import Path

ITEM_RE = re.compile(r"^- #(\d+) \[")
HEADING_RE = re.compile(r"^## (.+?)\s*$")
DONE_RE = re.compile(r"-> (?:DONE|CLOSED)\b")
BARE_ID_RE = re.compile(r"(?<![A-Za-z0-9/_.-])#(\d+)\b")
BLOCK_END_RE = re.compile(r"^(?:- |#)")


def _unfenced(text: str) -> list[str]:
    """Lines outside ``` fences - fenced examples quote the shapes as text."""
    out = []
    in_fence = False
    for raw in text.splitlines():
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(raw)
    return out


def _items(lines: list[str]) -> list[tuple[int, str | None, list[str]]]:
    """(id, section-name, block-lines) per item bullet. Section names come
    from line-anchored `## ` headings only; a block runs to the next
    column-0 `- ` bullet or heading, or end of lines - never a blank line."""
    items = []
    section = None
    i = 0
    n = len(lines)
    while i < n:
        m = HEADING_RE.match(lines[i])
        if m:
            section = m.group(1)
            i += 1
            continue
        bm = ITEM_RE.match(lines[i])
        if bm:
            j = i + 1
            while j < n and not BLOCK_END_RE.match(lines[j]):
                j += 1
            items.append((int(bm.group(1)), section, lines[i:j]))
            i = j
            continue
        i += 1
    return items


def lint_backlog(path: Path, requirements: Path | None = None) -> list[str]:
    findings: list[str] = []
    items = _items(_unfenced(path.read_text()))
    seen: set[int] = set()
    for num, _section, _block in items:
        if num in seen:
            findings.append(f"duplicate item #{num}")
        seen.add(num)
    for num, section, block in items:
        has_record = any(DONE_RE.search(l) for l in block)
        if section == "Done" and not has_record:
            findings.append(f"item #{num} under ## Done has no done record (-> DONE or -> CLOSED)")
        if section == "Open" and has_record:
            findings.append(f"item #{num} under ## Open carries a done record")
    if requirements is not None:
        for l in _unfenced(requirements.read_text()):
            if not l.startswith("|"):
                continue
            for m in BARE_ID_RE.finditer(l):
                if int(m.group(1)) not in seen:
                    findings.append(
                        f"{requirements.name}: #{m.group(1)} resolves to no backlog item"
                    )
    return findings


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Structural lint for the backlog file")
    parser.add_argument("file", type=Path, help="backlog.md to lint")
    parser.add_argument("--requirements", type=Path, default=None,
                        help="requirements contract whose #N citations are cross-checked")
    ns = parser.parse_args(argv)
    findings = lint_backlog(ns.file, ns.requirements)
    for f in findings:
        print(f)
    raise SystemExit(1 if findings else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
