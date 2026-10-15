# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Provenance-commit gate for an accepted research-lab experiment (D8).

The only way a lab member turns an accepted experiment into a commit: never a
hand-run ``git commit`` for this, and never ``--no-verify`` (D8 originally
allowed skipping hooks; hooks now run on everything except ``--data`` files).

Checks, in order - the first failure aborts with nothing committed:

1. accepted: the experiment is marked accepted - a decisions.md D entry whose
   text accepts it (pilot format ``**R4 accepted (E1-E4).**``; single ids and
   id-ranges both read), or a ``[x]`` state in the status.md experiment table
   (the index).
2. silent-deletion guard: the staged diff may not delete lines from any
   accepted entry in the lab's experiment files (``experiments.md`` or
   ``experiments/<eid>.md``) - a member once regenerated a shared experiments
   file and dropped an accepted entry (230 deleted lines nobody read). The
   deleted lines are reported with their old line numbers.
3. pre-commit hooks: when the repo has a ``.pre-commit-config.yaml`` they run
   on every path except the ``--data`` ones (frozen, hash-cited files a hook
   would rewrite); data paths are committed too and listed in the commit body.
4. lab lint: ``lab_lint.py`` on the lab dir must be clean (future stamps,
   status shape, audit vocabulary).
5. gated commit, one chained command so a fresh env check decides:
   ``printenv COMMIT_AUTHORISED >/dev/null && git commit ...``. The var is
   never set here; without it nothing is committed and the paths stay staged.
6. the commit SHA is written into the entry's ``Provenance`` line
   (`` `exp:` commit <SHA> ``) and left uncommitted for the next docs commit -
   the lab's Finish step commits all lab files, and this keeps the ``exp:``
   commit byte-exact as-run.

Usage:
    uv run --script lab_commit.py <lab-dir> <exp-id> [--data <path>...] -- <paths...>

Paths are resolved against the current directory and must live in the lab's
git repo; ``--data`` paths must also appear in the commit paths. Exits 0 only
when the commit was made; every refusal names the failed check and what to do.
"""

from __future__ import annotations

import argparse
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
LAB_LINT = SCRIPTS / "lab_lint.py"

ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
D_LINE_RE = re.compile(r"^\s*-\s*D\d+\b")
# "E1-E4" (or "E1-4") inside an accepted D entry expands to every id it covers
ID_RANGE_RE = re.compile(r"\b([A-Za-z]+)(\d+)\s*-\s*(?:[A-Za-z]+)?(\d+)\b")


def _die(msg: str) -> None:
    print(f"lab-commit: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _git(workdir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(
        ["git", "-C", str(workdir), *args], capture_output=True, text=True
    )
    if check and p.returncode:
        _die(f"git {' '.join(args[:2])} failed: {(p.stderr or p.stdout).strip()}")
    return p


def _accepted_ids(lab: Path) -> set[str]:
    """Every id the lab marks accepted: decisions.md D entries + the status index."""
    ids: set[str] = set()
    decisions = lab / "decisions.md"
    if decisions.is_file():
        for line in decisions.read_text().splitlines():
            if "accepted" not in line.lower() or not D_LINE_RE.match(line):
                continue
            for m in ID_RANGE_RE.finditer(line):
                lo, hi = int(m.group(2)), int(m.group(3))
                if lo <= hi and hi - lo < 1000:
                    ids.update(f"{m.group(1)}{i}" for i in range(lo, hi + 1))
            ids.update(re.findall(r"[A-Za-z][A-Za-z0-9_-]*", line))
    status = lab / "status.md"
    if status.is_file():
        for line in status.read_text().splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 4 and cells[0] and "[x]" in cells[3]:
                ids.add(cells[0])
    return ids


def _title_from(rest: str) -> str:
    rest = re.sub(r"^\s*\([^)]*\)\s*\.?\s*", "", rest)  # pilot "(date). " prefix
    rest = rest.lstrip(":").strip()
    return re.sub(r"\s*-\s*done$", "", rest)


def _find_entry(lab: Path, exp_id: str) -> tuple[Path, int, int, str]:
    """(entry file, 0-based heading line, heading level, title) for exp_id."""
    cands: list[Path] = [lab / "experiments" / f"{exp_id}.md", lab / "experiments.md"]
    if (lab / "experiments").is_dir():
        cands += sorted((lab / "experiments").glob("*.md"))
    pat = re.compile(rf"^(#{{1,6}})\s+{re.escape(exp_id)}(?![\w.-])(.*)$")
    seen: set[Path] = set()
    for f in cands:
        if f in seen or not f.is_file():
            continue
        seen.add(f)
        for i, line in enumerate(f.read_text().splitlines()):
            m = pat.match(line)
            if m:
                title = _title_from(m.group(2))
                if not title:
                    _die(f"entry heading for {exp_id} in {f} has no title to put in the commit message")
                return f, i, len(m.group(1)), title
    _die(
        f"no entry heading for {exp_id} in {lab}/experiments/ or {lab}/experiments.md - "
        "the worker writes experiments/<id>.md (or an experiments.md section) before the commit"
    )
    raise AssertionError  # unreachable; _die exits


def _entry_end(lines: list[str], head: int, level: int) -> int:
    """Index one past the entry's last line (next heading of level <= its own)."""
    for j in range(head + 1, len(lines)):
        m = re.match(r"^(#{1,6})\s", lines[j])
        if m and len(m.group(1)) <= level:
            return j
    return len(lines)


def _staged_experiment_files(lab: Path, repo: Path) -> list[str]:
    """Repo-relative staged files that are the lab's experiment files."""
    rels = []
    for rel in _git(repo, "diff", "--cached", "--name-only").stdout.splitlines():
        try:
            inlab = (repo / rel).relative_to(lab)
        except ValueError:
            continue
        if inlab == Path("experiments.md") or (
            len(inlab.parts) == 2 and inlab.parts[0] == "experiments" and inlab.suffix == ".md"
        ):
            rels.append(rel)
    return rels


def _entry_regions(text: str, accepted: set[str]) -> dict[str, list[tuple[int, int]]]:
    """1-based (inclusive) line spans of each accepted entry's heading section."""
    lines = text.splitlines()
    heads = [
        (i + 1, len(m.group(1)), m.group(2))
        for i, line in enumerate(lines)
        if (m := re.match(r"^(#{1,6})\s+(.+?)\s*$", line))
    ]
    regions: dict[str, list[tuple[int, int]]] = {}
    for j, (ln, level, txt) in enumerate(heads):
        tok = re.match(r"([A-Za-z][A-Za-z0-9_-]*)", txt)
        if not tok or tok.group(1) not in accepted:
            continue
        end = next((h[0] - 1 for h in heads[j + 1 :] if h[1] <= level), len(lines))
        regions.setdefault(tok.group(1), []).append((ln, end))
    return regions


def _staged_deletions(repo: Path, rel: str) -> list[tuple[int, str]]:
    """(old line number, deleted text) from the staged diff of one file."""
    diff = _git(repo, "diff", "--cached", "-U0", "--", rel).stdout
    deletions: list[tuple[int, str]] = []
    old = None
    for line in diff.splitlines():
        m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if m:
            old = int(m.group(1))
        elif line.startswith(("diff ", "index ", "--- ", "+++ ")):
            continue
        elif old is not None and line.startswith("-"):
            deletions.append((old, line[1:]))
            old += 1
        elif old is not None and not line.startswith("+"):
            old += 1
    return deletions


def check_deletions(lab: Path, repo: Path, accepted: set[str]) -> list[str]:
    """Report lines the staged diff would delete from accepted entries."""
    report = []
    for rel in _staged_experiment_files(lab, repo):
        head = _git(repo, "show", f"HEAD:{rel}", check=False)
        if head.returncode:
            continue  # not in HEAD (new file, or no commits yet): nothing to delete
        regions = _entry_regions(head.stdout, accepted)
        if not regions:
            continue
        hits = [
            (eid, ln, txt)
            for ln, txt in _staged_deletions(repo, rel)
            for eid, spans in regions.items()
            if any(a <= ln <= b for a, b in spans)
        ]
        for eid in {h[0] for h in hits}:
            lines = [h for h in hits if h[0] == eid]
            report.append(f"  {rel}:{lines[0][1]}: accepted entry {eid} loses {len(lines)} line(s):")
            report += [f"    {ln}: {txt[:100]}" for _, ln, txt in lines[:10]]
    return report


def run_hooks(repo: Path, hook_paths: list[str]) -> None:
    config = repo / ".pre-commit-config.yaml"
    if not config.is_file():
        print("no .pre-commit-config.yaml - hooks skipped")
        return
    if not hook_paths:
        print("every path is a --data file - hooks skipped")
        return
    pre = shutil.which("pre-commit")
    cmd = [pre] if pre else ["uv", "run", "--no-project", "--with", "pre-commit", "pre-commit"]
    p = subprocess.run(
        cmd + ["run", "--files", *hook_paths], cwd=repo, capture_output=True, text=True
    )
    if p.returncode:
        _die(f"pre-commit hooks failed (fix and re-run; never --no-verify):\n{p.stdout}{p.stderr}")
    print(f"pre-commit hooks passed on {len(hook_paths)} path(s)")


def run_lint(lab: Path) -> None:
    p = subprocess.run([sys.executable, str(LAB_LINT), str(lab)], capture_output=True, text=True)
    if p.returncode:
        _die(f"lab lint failed (fix the findings, then re-run):\n{p.stdout}{p.stderr}")
    print("lab lint: clean")


def gated_commit(repo: Path, subject: str, body: str, rels: list[str]) -> str:
    """Commit through the env gate as ONE chained command; returns the new SHA."""
    before = _git(repo, "rev-parse", "HEAD", check=False).stdout
    parts = ["git", "commit", "-m", subject]
    if body:
        parts += ["-m", body]
    parts += ["--", *rels]
    chain = "printenv COMMIT_AUTHORISED >/dev/null && " + " ".join(shlex.quote(p) for p in parts)
    p = subprocess.run(["bash", "-c", chain], cwd=repo, capture_output=True, text=True)
    if p.returncode:
        # printenv stopped the chain (HEAD unchanged, nothing printed) = the gate is
        # closed; any output means git itself ran and refused
        if not (p.stdout or p.stderr) and _git(repo, "rev-parse", "HEAD", check=False).stdout == before:
            _die(
                "COMMIT_AUTHORISED not set - no commit made (D8: member sessions launch with "
                "it in env). Set it in the member session's environment and re-run; the paths stay staged."
            )
        _die(f"git commit failed:\n{p.stdout}{p.stderr}")
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def write_provenance_sha(entry: Path, head: int, level: int, sha: str) -> None:
    """Write the commit SHA into this entry's Provenance line; leave it uncommitted."""
    lines = entry.read_text().splitlines()
    end = _entry_end(lines, head, level)
    for j in range(head, end):
        if "**Provenance:**" in lines[j]:
            line = lines[j]
            m = re.search(r"(`exp:` commit )[^;`\n]*", line)
            if m:
                lines[j] = re.sub(r"(`exp:` commit )[^;`\n]*", rf"\g<1>{sha}", line, count=1)
            else:
                lines[j] = line.rstrip() + f"; `exp:` commit {sha}"
            entry.write_text("\n".join(lines) + "\n")
            return
    _die(
        f"no '**Provenance:**' line in {entry}'s Entry section - add the template's "
        f"Provenance line and fill the SHA by hand: `exp:` commit {sha} (the commit is already made)"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="lab-commit",
        description="Gated provenance commit for an accepted research-lab experiment.",
    )
    ap.add_argument("lab_dir", help="the lab directory")
    ap.add_argument("exp_id", help="experiment id, e.g. E1")
    ap.add_argument(
        "--data",
        nargs="+",
        default=[],
        metavar="PATH",
        help="frozen/hash-cited files: committed, but excluded from hooks and listed in the body",
    )
    ap.add_argument("paths", nargs="+", metavar="PATH", help="files to commit (after --)")
    args = ap.parse_args()

    lab = Path(args.lab_dir).resolve()
    if not lab.is_dir():
        _die(f"not a directory: {lab}")
    if not ID_RE.fullmatch(args.exp_id):
        _die(f"bad experiment id {args.exp_id!r}")
    repo = Path(_git(lab, "rev-parse", "--show-toplevel").stdout.strip())

    rels, data_rels = [], []
    for raw in args.paths:
        p = Path(raw).resolve()
        if not p.exists():
            _die(f"path not found: {raw}")
        try:
            rels.append(p.relative_to(repo).as_posix())
        except ValueError:
            _die(f"{raw} is outside the lab's repo ({repo})")
    for raw in args.data:
        try:
            data_rels.append(Path(raw).resolve().relative_to(repo).as_posix())
        except ValueError:
            _die(f"--data path {raw} is outside the lab's repo ({repo})")
    stray = [d for d in data_rels if d not in rels]
    if stray:
        _die(f"--data paths must also be commit paths: {', '.join(stray)}")

    accepted = _accepted_ids(lab)
    if args.exp_id not in accepted:
        _die(
            f"{args.exp_id} is not marked accepted - no decisions.md D entry accepts it and "
            "its status.md index row is not [x]. Only accepted experiments get a provenance commit."
        )
    print(f"{args.exp_id}: accepted (decisions.md D entries / status.md index)")

    entry, head, level, title = _find_entry(lab, args.exp_id)
    print(f"entry: {entry} ({title!r})")

    _git(repo, "add", "--", *rels)
    report = check_deletions(lab, repo, accepted)
    if report:
        _die(
            "refusing - the staged diff deletes lines from an accepted experiment entry "
            "(the silent-deletion guard; a regenerated experiments file once dropped one):\n"
            + "\n".join(report)
            + "\nRestore the entry, or take the deletion to the overseer as an explicit revert."
        )
    print("silent-deletion guard: no accepted entry loses lines")

    run_hooks(repo, [r for r in rels if r not in data_rels])
    run_lint(lab)

    subject = f"exp: {args.exp_id} {title}"
    body = f"data files (hook-exempt): {', '.join(data_rels)}" if data_rels else ""
    sha = gated_commit(repo, subject, body, rels)
    print(f"committed {sha[:12]}: {subject}")

    write_provenance_sha(entry, head, level, sha)
    print(
        f"wrote `exp:` commit {sha} into {entry}'s Provenance line - left uncommitted "
        "for the next docs commit (the lab's Finish step commits all lab files)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
