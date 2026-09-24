"""Read-only configuration and native prerequisite diagnostics."""

from pathlib import Path
import shutil

from settings_sync.paths import Paths
from settings_sync.registry import Harness, run_harness
from settings_sync.sync import Outcome, Status


def doctor(paths: Paths, harnesses: tuple[Harness, ...]) -> list[Outcome]:
    outcomes = [Outcome(paths.source_dir, Status.UNCHANGED, "effective source checkout; edit shared configuration here")]
    for harness in harnesses:
        target = harness.destination(paths)
        if target is None:
            continue
        outcomes.append(Outcome(target, Status.UNCHANGED, f"{harness.name} runtime destination"))
        host = shutil.which(harness.host)
        outcomes.append(Outcome(target, Status.UNCHANGED if host else Status.NO_SOURCE,
                                f"host CLI: {host}" if host else f"optional host CLI unavailable: {harness.host}; config generation is available"))
        for outcome in run_harness(harness, paths, False, True):
            if outcome.status not in (Status.UNCHANGED, Status.NO_SOURCE, Status.FAILED):
                outcome.detail += f"; run agent-config sync {harness.name}"
            outcomes.append(outcome)
        if harness.validate_skills:
            outcomes.extend(harness.validate_skills(paths.source_dir / "skills"))
    skills = paths.source_dir / "skills"
    if skills.is_dir():
        for path in skills.rglob("*"):
            if path.is_symlink() and not path.exists():
                outcomes.append(Outcome(path, Status.FAILED, "broken source link; run git submodule update --init --recursive in the source checkout, then verify the link"))
    return outcomes
