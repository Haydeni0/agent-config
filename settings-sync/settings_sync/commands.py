"""Sync real commands + generate skill-command stubs into ~/.config/opencode/commands/."""

from pathlib import Path

from settings_sync.frontmatter import dump, parse
from settings_sync.actions import Action, File, Prune, Report, Status


def _build_skill_stub(skill_md: Path) -> str | None:
    frontmatter, _ = parse(skill_md.read_text())
    name = frontmatter.get("name")
    description = frontmatter.get("description", "")
    if not name:
        return None
    body = f'Invoke the `skill` tool with name "{name}" to load and apply it. $ARGUMENTS\n'
    return dump({"description": description}, body)


def plan_commands(target_dir: Path, source_dir: Path, skills_dir: Path) -> list[Action]:
    if not source_dir.is_dir():
        return [Report(source_dir, Status.FAILED, "required commands source directory missing; restore before syncing")]
    actions: list[Action] = []
    expected_names: set[str] = set()

    for source_file in sorted(source_dir.glob("*.md"), key=lambda p: p.name):
        if not source_file.is_file():
            continue
        expected_names.add(source_file.name)
        actions.append(File(target_dir / source_file.name, source_file.read_text()))

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
            actions.append(File(target_dir / name, stub))

    actions.append(Prune(target_dir, frozenset(expected_names)))
    return actions
