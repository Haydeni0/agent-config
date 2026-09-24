"""Validate ~/.claude/skills for opencode compatibility (warn only, never fix)."""

import re
from pathlib import Path

from settings_sync.frontmatter import parse
from settings_sync.sync import Outcome, Status

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def validate_skills(skills_dir: Path) -> list[Outcome]:
    outcomes: list[Outcome] = []
    if not skills_dir.is_dir():
        return outcomes
    for skill_dir in sorted(skills_dir.iterdir(), key=lambda p: p.name):
        if not skill_dir.is_dir():
            continue
        name = skill_dir.name
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file() and any(skill_dir.rglob("SKILL.md")):
            continue
        if not skill_md.is_file():
            outcomes.append(Outcome(skill_dir, Status.WARNED, f"{name}: missing SKILL.md, opencode will skip"))
            continue
        frontmatter, _ = parse(skill_md.read_text())
        fm_name = frontmatter.get("name")
        if not fm_name:
            outcomes.append(Outcome(skill_md, Status.WARNED, f"{name}: frontmatter missing 'name'"))
            continue
        if fm_name != name:
            outcomes.append(
                Outcome(skill_md, Status.WARNED, f"{name}: frontmatter name '{fm_name}' != dir name '{name}'")
            )
        if not NAME_RE.match(str(fm_name)):
            outcomes.append(Outcome(skill_md, Status.WARNED, f"{name}: name '{fm_name}' fails opencode regex"))
        if not frontmatter.get("description"):
            outcomes.append(Outcome(skill_md, Status.WARNED, f"{name}: frontmatter missing 'description'"))
    return outcomes
