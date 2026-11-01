import pathlib

import pytest

from settings_sync.skills import validate_skills
from settings_sync.actions import Status


def _make_skill(
    skills_dir: pathlib.Path, name: str, frontmatter_name: str | None = None, description: str = "desc"
) -> pathlib.Path:
    d = skills_dir / name
    d.mkdir(parents=True)
    fm_name = frontmatter_name if frontmatter_name is not None else name
    (d / "SKILL.md").write_text(f"---\nname: {fm_name}\ndescription: {description}\n---\nBody.\n")
    return d


def test_valid_skill_no_warnings(tmp_path: pathlib.Path):
    _make_skill(tmp_path, "uv")
    assert validate_skills(tmp_path) == []


def test_warns_when_frontmatter_name_mismatches_dir(tmp_path: pathlib.Path):
    _make_skill(tmp_path, "compress", frontmatter_name="caveman-compress")
    outcomes = validate_skills(tmp_path)
    assert len(outcomes) == 1
    assert outcomes[0].status == Status.WARNED
    assert "compress" in outcomes[0].detail
    assert "caveman-compress" in outcomes[0].detail


def test_warns_when_skill_md_missing(tmp_path: pathlib.Path):
    d = tmp_path / "no-skill-md"
    d.mkdir()
    (d / "reference.md").write_text("no skill here")
    outcomes = validate_skills(tmp_path)
    assert any(o.status == Status.WARNED and "SKILL.md" in o.detail for o in outcomes)


def test_warns_when_name_invalid(tmp_path: pathlib.Path):
    _make_skill(tmp_path, "Bad_Name")
    outcomes = validate_skills(tmp_path)
    assert any(o.status == Status.WARNED and "Bad_Name" in o.detail for o in outcomes)
