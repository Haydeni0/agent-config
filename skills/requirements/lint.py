#!/usr/bin/env python3
"""Lint a binding requirements contract table: duplicate IDs and citation resolution.

Usage: python lint.py <contract.md> [repo_root]
Exit 0 = clean; exit 1 prints one finding per line, "<row ID>: <finding>".
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Backtick-quoted tokens that look like repo paths (test/script/doc files).
CITATION = re.compile(r"`([^`]+\.\w+)`")
ID = re.compile(r"^\| (REQ-[A-Z0-9-]+) +\|")
# File extensions we resolve; prose/backlog refs are not citations.
RESOLVABLE = {".py", ".mjs", ".js", ".sh", ".json", ".md", ".toml", ".yml"}
# Walk roots to prune from bare-filename search.
SKIP_DIRS = {".git", "node_modules", ".venv"}


def parse_rows(md_text: str) -> list[tuple[str, str, str]]:
    """Return (id, statement, verification) for each contract table row."""
    rows: list[tuple[str, str, str]] = []
    for line in md_text.splitlines():
        match = ID.match(line)
        if not match or "-|-" in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split(" | ")]
        if len(cells) >= 3:
            rows.append((match.group(1), cells[1], " ".join(cells[2:])))
    return rows


def _resolves(token: str, root: Path) -> bool:
    """A citation resolves when the named file exists at the root or anywhere in it.

    `test.py::test_name` selectors resolve via the file part; globs are skipped
    (not statically resolvable); bare filenames (command.test.mjs) are searched
    for by name so per-repo test layouts need no configuration.
    """
    name = token.split("::")[0].split(" ")[0]
    if "*" in name or Path(name).suffix not in RESOLVABLE:
        return True
    if "/" in name:
        return (root / name).is_file()
    if (root / name).is_file():
        return True
    return any(
        candidate.is_file() and not any(part in SKIP_DIRS for part in candidate.parts)
        for candidate in root.rglob(name)
    )


def findings(rows: list[tuple[str, str, str]], root: Path) -> list[str]:
    """Return one human-readable finding string per defect, empty when clean."""
    found: list[str] = []
    seen: dict[str, str] = {}
    for row_id, _statement, verification in rows:
        if row_id in seen:
            found.append(f"{row_id}: duplicate ID (first at {seen[row_id]})")
        else:
            seen[row_id] = row_id
        if "manual" in verification or "planned" in verification:
            continue
        for token in CITATION.findall(verification):
            if not _resolves(token, root):
                found.append(f"{row_id}: citation does not resolve: {token}")
    return found


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print("usage: lint.py <contract.md> [repo_root]", file=sys.stderr)
        return 2
    contract = Path(argv[1])
    root = Path(argv[2]) if len(argv) == 3 else contract.parent
    found = findings(parse_rows(contract.read_text()), root)
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
