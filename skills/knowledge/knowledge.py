#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Mechanical surface over the knowledge store: search, add, sweep.

The store's contract (AGENTS.md at the store root) owns every rule; this
tool only enforces the mechanical parts so sessions cannot drift:

  search <query words>   print entries whose claim/scope/links match
  add                    read a proposed entry on stdin, enforce the
                         fixed parts + the admission gate, then append
  sweep                  flag entries whose how-verified names paths
                         that no longer exist, and environment facts
                         older than the sweep cadence

Usage:
  knowledge.py search <word> [<word> ...]
  knowledge.py add < domain.md < proposed.md
  knowledge.py sweep [--env-max-age-days N]

The store root is ~/gitrepos/knowledge unless KNOWLEDGE_STORE is set.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

PARTS = ("claim", "kind", "project", "source", "how-verified", "level", "date", "scope", "links")
REQUIRED = ("claim", "kind", "source", "how-verified", "level", "date", "scope")
LEVELS = ("replicated", "audited", "observed", "cited", "superseded")
KINDS = ("fact", "finding", "pattern", "ruling", "method")
# admission gate: source must not point at gitignored scratch
SCRATCH_RE = re.compile(r"\.agents/work/|/tmp/|state/improvement-log")
MAX_AGE_DEFAULT_DAYS = 365


def store() -> Path:
    root = Path(os.environ.get("KNOWLEDGE_STORE", "~/gitrepos/knowledge")).expanduser()
    if not (root / "AGENTS.md").is_file():
        sys.exit(f"knowledge: no AGENTS.md under {root} - not a knowledge store")
    return root


def entries(root: Path):
    """(domain file, entry text, first line) per entry bullet in the store."""
    for f in sorted(root.glob("*.md")):
        if f.name in ("AGENTS.md", "index.md", "sweep-log.md"):
            continue
        lines = f.read_text(errors="replace").splitlines(keepends=True)
        i = 0
        while i < len(lines):
            if lines[i].startswith("- claim:"):
                j = i + 1
                while j < len(lines) and not lines[j].startswith("- claim:") and (
                    lines[j].startswith(("  ", "\t")) or lines[j].strip() == ""
                ):
                    j += 1
                yield f, "".join(lines[i:j]), lines[i].rstrip("\n")
                i = j
            else:
                i += 1


def cmd_search(words: list[str]) -> int:
    root = store()
    hits = 0
    for f, text, first in entries(root):
        low = text.lower()
        if all(w.lower() in low for w in words):
            hits += 1
            print(f"{f.name}: {first}")
            for line in text.splitlines()[1:]:
                if any(p + ":" in line for p in PARTS):
                    print("  " + line.strip())
            print()
    print(f"{hits} hit(s)")
    return 0


def parse_entry(text: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^- (\w[\w-]*): (.*)$", line) or re.match(r"^  (\w[\w-]*): (.*)$", line)
        if m and m.group(1) in PARTS:
            if m.group(1) in parts:
                sys.exit(f"knowledge: duplicate part {m.group(1)}")
            parts[m.group(1)] = m.group(2).strip()
    return parts


def cmd_add(domain: str) -> int:
    root = store()
    domain = domain.removesuffix(".md")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", domain):
        sys.exit(f"knowledge: bad domain name {domain!r}")
    text = sys.stdin.read()
    parts = parse_entry(text)
    missing = [p for p in REQUIRED if p not in parts]
    if missing:
        sys.exit(f"knowledge: missing required parts: {', '.join(missing)}")
    unknown = [p for p in parts if p not in PARTS]
    if unknown:
        sys.exit(f"knowledge: unknown parts: {', '.join(unknown)}")
    if parts["kind"] not in KINDS:
        sys.exit(f"knowledge: kind must be one of {', '.join(KINDS)}")
    if parts["level"] not in LEVELS:
        sys.exit(f"knowledge: level must be one of {', '.join(LEVELS)}")
    if SCRATCH_RE.search(parts["source"]):
        sys.exit(f"knowledge: source points at scratch/gitignored state: {parts['source']}")
    # admission gate: every existing artifact path named in source or
    # how-verified must resolve (commit SHAs and URLs pass untouched)
    for field in ("source", "how-verified"):
        for token in re.findall(r"(?:(?<=\s)|(?<=^))[~/][^\s,;)]+", parts[field]):
            p = Path(os.path.expanduser(token.rstrip(".,;")))
            if p.is_absolute() or p.exists():
                continue  # an existing path, or a shape we cannot check
            if re.search(r"\b[0-9a-f]{7,40}\b", token) or token.startswith(("http", "ssh://")):
                continue
            if p.suffix in ("", ".md", ".py", ".json", ".log", ".sh", ".txt") and "/" in str(p):
                sys.exit(f"knowledge: {field} names a path that does not exist: {token}")
    try:
        datetime.strptime(parts["date"], "%Y-%m-%d")
        if parts["date"] > date.today().isoformat():
            sys.exit("knowledge: date is in the future")
    except ValueError:
        sys.exit("knowledge: date must be YYYY-MM-DD from `date`")
    # dedupe: same claim text already present -> NOOP naming it
    claim = parts["claim"].lower()
    for f, text_e, first in entries(root):
        if f"claim: {claim}" in text_e.lower() or f"- claim: {claim}" == first.lower():
            print(f"NOOP: {f.name} already holds this claim: {first}")
            return 0
    target = root / f"{domain}.md"
    if not target.is_file():
        target.write_text(f"# {domain}\n\n")
        print(f"knowledge: created {target.name}")
    order = [p for p in PARTS if p in parts and p != "claim"]
    body = "- claim: " + parts["claim"] + "\n" + "".join(
        f"  {p}: {parts[p]}\n" for p in order
    )
    with target.open("a") as fh:
        fh.write("\n" + body if target.stat().st_size > 0 else body)
    print(f"ADD: {domain}.md <- {parts['claim'][:80]}")
    return 0


def cmd_sweep(env_max_age_days: int) -> int:
    root = store()
    flags = 0
    today = date.today()
    for f, text, first in entries(root):
        parts = parse_entry(text)
        # rule 6: the how-verified paths must still exist
        for token in re.findall(r"(?:(?<=\s)|(?<=^))[~/][^\s,;)]+", parts.get("how-verified", "")):
            p = Path(os.path.expanduser(token.rstrip(".,;")))
            if "/" in str(p) and not (
                p.exists()
                or re.search(r"\b[0-9a-f]{7,40}\b", token)
                or token.startswith(("http", "ssh://"))
            ):
                if p.suffix in ("", ".md", ".py", ".json", ".log", ".sh", ".txt"):
                    print(f"FLAG {f.name}: missing how-verified artifact {token} in: {first}")
                    flags += 1
        # environment facts carry a re-validation clock
        if parts.get("kind") == "fact" and parts.get("level") in ("observed", "audited"):
            try:
                age = (today - datetime.strptime(parts["date"], "%Y-%m-%d").date()).days
            except ValueError:
                continue
            if age > env_max_age_days:
                print(f"FLAG {f.name}: environment fact {age} days old: {first}")
                flags += 1
    if flags:
        print(f"{flags} flag(s); recorded to sweep-log.md - the PI decides, nothing is edited")
        with (root / "sweep-log.md").open("a") as fh:
            fh.write(f"\n- {today.isoformat()}: sweep flagged {flags} entr(ies); see output above\n")
    else:
        print("no flags")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("search", "add", "sweep"):
        print(__doc__)
        return 2
    if argv[1] == "search":
        if len(argv) < 3:
            print("knowledge: search needs at least one word")
            return 2
        return cmd_search(argv[2:])
    if argv[1] == "add":
        if len(argv) != 3:
            print("knowledge: add needs exactly the domain file name (entry on stdin)")
            return 2
        return cmd_add(argv[2])
    days = MAX_AGE_DEFAULT_DAYS
    if "--env-max-age-days" in argv:
        i = argv.index("--env-max-age-days")
        days = int(argv[i + 1])
    return cmd_sweep(days)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
