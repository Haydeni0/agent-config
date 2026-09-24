"""Sync real commands + generate skill-command stubs into ~/.config/opencode/commands/."""

from pathlib import Path

from settings_sync.frontmatter import parse
from settings_sync.sync import Outcome, Status
from settings_sync.ownership import prune_generated, sync_generated_file


def _build_skill_stub(skill_md: Path) -> str | None:
    frontmatter, _ = parse(skill_md.read_text())
    name = frontmatter.get("name")
    description = frontmatter.get("description", "")
    if not name:
        return None
    return (
        f"---\ndescription: {description}\n---\n\n"
        f"Invoke the `skill` tool with name \"{name}\" to load and apply it. $ARGUMENTS\n"
    )


def sync_commands(
    target_dir: Path,
    source_dir: Path,
    skills_dir: Path,
    force: bool = False,
    dry_run: bool = False,
) -> list[Outcome]:
    if not source_dir.is_dir():
        return [Outcome(source_dir, Status.FAILED, "required commands source directory missing; restore before syncing")]
    outcomes: list[Outcome] = []
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    expected_names: set[str] = set()

    for source_file in sorted(source_dir.glob("*.md"), key=lambda p: p.name):
        if not source_file.is_file():
            continue
        expected_names.add(source_file.name)
        outcomes.append(sync_generated_file(target_dir / source_file.name, source_file.read_text(), force, dry_run))

    if skills_dir.is_dir():
        for skill_dir in sorted(skills_dir.iterdir(), key=lambda p: p.name):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            stub = _build_skill_stub(skill_md)
            if stub is None:
                continue
            name = skill_dir.name + ".md"
            if name in expected_names:
                continue
            expected_names.add(name)
            outcomes.append(sync_generated_file(target_dir / name, stub, force, dry_run))

    outcomes.extend(prune_generated(target_dir, expected_names, dry_run))
    return outcomes
