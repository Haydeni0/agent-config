#!/usr/bin/env python3
"""Lint a binding requirements contract table: duplicate IDs and citation resolution.

Usage: python lint.py <contract.md> [repo_root]
repo_root defaults to the current working directory - run from the repo root.
Exit 0 = clean; 1 = findings, one per line "<row ID>: <finding>";
2 = no contract rows parsed (wrong file or unknown ID scheme).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Backtick-quoted tokens ending in a file-extension-shaped suffix (.py, .mjs, .yaml, ...).
CITATION = re.compile(r"`([^`]+\.\w+)`")
# Any scheme-shaped ID: uppercase area plus dashed or dotted numbering (REQ-SYNC-01, FR-1, SR-03).
ID = re.compile(r"^\| ([A-Z][A-Z0-9]+(?:[-.][A-Z0-9]+)+) +\|")
# manual (...) spans hold procedures, not citations; the bare word "planned" marks an unbuilt pointer.
MANUAL_SPAN = re.compile(r"manual\s*\([^)]*\)")
PLANNED = re.compile(r"\bplanned\b")
# Directories pruned from the filename walk.
SKIP_DIRS = {".git", "node_modules", ".venv"}
# Extension-shaped suffix: 1-5 chars (py, mjs, yaml, cfg); longer dotted
# words (native.unchanged) are field names, not file citations.
SHORT_EXT = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,4}$")


def parse_rows(md_text: str) -> list[tuple[int, str, str, str]]:
    """Return (line_no, id, statement, verification) for each contract table row."""
    rows: list[tuple[int, str, str, str]] = []
    for line_no, line in enumerate(md_text.splitlines(), 1):
        match = ID.match(line)
        if not match or "-|-" in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split(" | ")]
        if len(cells) >= 3:
            rows.append((line_no, match.group(1), cells[1], " ".join(cells[2:])))
    return rows


def _file_index(root: Path) -> set[str]:
    """Every filename under root, from one walk that prunes SKIP_DIRS in place."""
    names: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        names.update(filenames)
    return names


def _is_citation(token: str) -> bool:
    """A backticked token is a citation only when path-shaped or extension-shaped.

    Globs are skipped (not statically resolvable); dotted non-file tokens
    (native.unchanged, 2.10.0) fail the short-extension test.
    """
    if "*" in token:
        return False
    name = token.split("::")[0].split(" ")[0]
    return "/" in token or bool(SHORT_EXT.search(name))


def _resolves(token: str, root: Path, names: set[str]) -> bool:
    """A citation resolves when its file exists at the root or anywhere under it.

    `test.py::test_name` selectors resolve via the file part; bare filenames
    (command.test.mjs) match the filename index so per-repo test layouts need
    no configuration.
    """
    name = token.split("::")[0].split(" ")[0]
    if "/" in name:
        return (root / name).is_file()
    return name in names or (root / name).is_file()


def findings(rows: list[tuple[int, str, str, str]], root: Path) -> list[str]:
    """Return one human-readable finding string per defect, empty when clean."""
    found: list[str] = []
    seen: dict[str, int] = {}
    names = _file_index(root)
    for line_no, row_id, _statement, verification in rows:
        if row_id in seen:
            found.append(f"{row_id}: duplicate ID (first at line {seen[row_id]})")
        else:
            seen[row_id] = line_no
        citations = PLANNED.sub(" ", MANUAL_SPAN.sub(" ", verification))
        for token in CITATION.findall(citations):
            if _is_citation(token) and not _resolves(token, root, names):
                found.append(f"{row_id}: citation does not resolve: {token}")
    return found


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print("usage: lint.py <contract.md> [repo_root]", file=sys.stderr)
        return 2
    contract = Path(argv[1])
    root = Path(argv[2]).resolve() if len(argv) == 3 else Path.cwd()
    rows = parse_rows(contract.read_text())
    if not rows:
        print(f"no contract rows parsed in {contract} - wrong file or unknown ID scheme", file=sys.stderr)
        return 2
    found = findings(rows, root)
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
