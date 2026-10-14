"""Lint .agents/work/* packages: state line, fix-attempts, marker grammar
and position (REQ-SKILLS-14). Reads, never writes. Fail-closed: malformed
input is a finding, never a silent pass."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_states import ALL_STATES, DEBUG_STATES  # noqa: E402

STATE_RE = re.compile(r"^state: ([a-z0-9-]+)$")
FIX_RE = re.compile(r"^fix-attempts: (\d+)$")
REVIEWED_RE = re.compile(r"^Reviewed: (pass|fail) ([1-9]\d*)$")
IMPLEMENTED_RE = re.compile(r"^Implemented$")


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
        findings.append(f"{rel}: fix-attempts forbidden in non-debug state {state!r}")
    for heading in ("## Outcome", "## Review nits"):
        base = heading[3:]
        for line in lines:
            s = line.rstrip()
            if re.match(rf"^#+\s*{re.escape(base)}\s*$", s) and s != heading:
                findings.append(f"{rel}: heading {base!r} must be exactly H2: {s[:30]!r}")
    return findings


def lint_markers(text: str, rel: str, is_plan: bool) -> list[str]:
    """Marker grammar is checked unconditionally (fail-closed: a malformed
    marker is a finding even when no valid marker exists). Position: markers
    must occupy a suffix of the non-empty lines. `Implemented` is a plan.md
    marker only."""
    findings = []
    nonempty = [l.strip() for l in text.splitlines() if l.strip()]
    marker_lines = [
        l for l in nonempty
        if REVIEWED_RE.match(l) or (is_plan and IMPLEMENTED_RE.match(l))
    ]
    for l in nonempty:
        if l.startswith("Reviewed:") and not REVIEWED_RE.match(l):
            findings.append(f"{rel}: malformed Reviewed marker: {l!r} (expected 'Reviewed: pass|fail <n>', n >= 1)")
        if is_plan and l.startswith("Implemented") and not IMPLEMENTED_RE.match(l):
            findings.append(f"{rel}: malformed Implemented marker: {l!r}")
    if marker_lines:
        block_start = nonempty.index(marker_lines[0])
        for l in nonempty[block_start + 1:]:
            if l not in marker_lines:
                findings.append(
                    f"{rel}: {marker_lines[0][:30]!r} must be a footer line - content after marker block: {l[:40]!r}"
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
    work_dir = Path(__file__).resolve().parent.parent / ".agents" / "work"
    findings = lint_all(work_dir)
    for f in findings:
        print(f"check-packages: {f}")
    print(f"check-packages: {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
