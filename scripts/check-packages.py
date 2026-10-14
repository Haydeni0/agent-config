"""Lint .agents/work/* packages: state line, fix-attempts, marker grammar
and position (REQ-SKILLS-14). Reads, never writes. Fail-closed: malformed
input is a finding, never a silent pass.

The repo's own .agents/work/ is machine-local (gitignored): a fresh CI
clone has no packages and this is a no-op there - the CI verification is
the unit tests; this run is the local gate. Pass --path <dir> to lint
another repo's package store."""

import importlib.util
import re
import sys
from pathlib import Path

STATE_RE = re.compile(r"^state: ([a-z0-9-]+)$")
FIX_RE = re.compile(r"^fix-attempts: (\d+)$")
REVIEWED_RE = re.compile(r"^Reviewed: (pass|fail) ([1-9]\d*)$")
IMPLEMENTED_RE = re.compile(r"^Implemented$")


def _load_package_states():
    spec = importlib.util.spec_from_file_location(
        "package_states", Path(__file__).resolve().parent / "package_states.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ps = _load_package_states()
ALL_STATES = _ps.ALL_STATES
DEBUG_STATES = _ps.DEBUG_STATES


def lint_decisions(text: str, rel: str) -> list[str]:
    findings = []
    lines = text.splitlines()
    first = lines[0].rstrip() if lines else ""
    m = STATE_RE.match(first)
    state = None
    if m:
        state = m.group(1)
        if state not in ALL_STATES:
            findings.append(f"{rel}: unknown state {state!r} (allowed: {' | '.join(sorted(ALL_STATES))})")
    elif first.strip().lower().startswith("state:"):
        findings.append(f"{rel}: malformed state line: {first[:40]!r} (expected 'state: <value>')")
    fix = None
    fix_reported = False
    # the fix-attempts line is legal ONLY at index 1, directly after state,
    # and only in exact grammar - anything else is a placement/grammar finding
    for i, raw in enumerate(lines):
        s = raw.strip()
        if not s.startswith("fix-attempts:"):
            continue
        fm = FIX_RE.match(s)
        if i == 1 and fm:
            fix = fm.group(1)
        else:
            findings.append(
                f"{rel}: fix-attempts line must sit directly after state and match 'fix-attempts: <integer>': {s[:40]!r}"
            )
            fix_reported = True
    if state in DEBUG_STATES:
        if fix is None and not fix_reported:
            findings.append(f"{rel}: fix-attempts required in debug state {state!r}")
    elif fix is not None:
        findings.append(f"{rel}: fix-attempts forbidden without a debug state (state: {state or 'no state line'})")
    for heading in ("## Outcome", "## Review nits"):
        base = heading[3:]
        for line in lines:
            s = line.rstrip()
            if re.match(rf"^#+\s*{re.escape(base)}\s*$", s) and s != heading:
                findings.append(f"{rel}: heading {base!r} must be exactly H2: {s[:30]!r}")
    return findings


def _unfenced_nonempty(text: str) -> list[str]:
    """Stripped non-empty lines outside ``` fences - fenced examples quote
    marker grammar as text, not as markers."""
    out: list[str] = []
    in_fence = False
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence and s:
            out.append(s)
    return out


def lint_markers(text: str, rel: str, is_plan: bool) -> list[str]:
    """`Reviewed:` grammar is checked on every unfenced line (fail-closed:
    a malformed marker is a finding even when no valid marker exists).
    `Implemented` is a marker only as an exact plan.md line - prose like
    "Implemented via X" is not a marker attempt. Position: markers must
    occupy a suffix of the unfenced non-empty lines, matched by index so a
    repeated identical marker line cannot misplace the block start."""
    findings = []
    nonempty = _unfenced_nonempty(text)
    marker_idx = {
        i for i, l in enumerate(nonempty)
        if REVIEWED_RE.match(l) or (is_plan and IMPLEMENTED_RE.match(l))
    }
    for l in nonempty:
        if l.startswith("Reviewed:") and not REVIEWED_RE.match(l):
            findings.append(f"{rel}: malformed Reviewed marker: {l!r} (expected 'Reviewed: pass|fail <n>', n >= 1)")
    if marker_idx:
        block_start = min(marker_idx)
        for i in range(block_start, len(nonempty)):
            if i not in marker_idx:
                findings.append(
                    f"{rel}: {nonempty[block_start][:30]!r} must be a footer line - content after marker block: {nonempty[i][:40]!r}"
                )
                break
    return findings


def lint_package(pkg: Path, root: Path) -> list[str]:
    findings = []
    decisions = pkg / "decisions.md"
    if decisions.exists():
        rel = str(decisions.relative_to(root))
        findings += lint_decisions(decisions.read_text(), rel)
    for name in ("spec.md", "plan.md"):
        p = pkg / name
        if p.exists():
            findings += lint_markers(p.read_text(), str(p.relative_to(root)), is_plan=(name == "plan.md"))
    return findings


def lint_all(work_dir: Path) -> list[str]:
    if not work_dir.exists():
        return []
    findings = []
    for pkg in sorted(work_dir.iterdir()):
        if pkg.is_dir():
            findings += lint_package(pkg, work_dir)
    return findings


def main() -> int:
    args = sys.argv[1:]
    if "--path" in args:
        work_dir = Path(args[args.index("--path") + 1])
    else:
        work_dir = Path(__file__).resolve().parent.parent / ".agents" / "work"
    findings = lint_all(work_dir)
    for f in findings:
        print(f"check-packages: {f}")
    print(f"check-packages: {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
