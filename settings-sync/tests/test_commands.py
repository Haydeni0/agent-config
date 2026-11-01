import pathlib

import pytest

from settings_sync.actions import Mode, Status
from settings_sync.commands import plan_commands
from settings_sync.executor import execute
from settings_sync.ownership import OwnershipStore


def apply_commands(target: pathlib.Path, source: pathlib.Path, skills: pathlib.Path, mode: Mode):
    store = OwnershipStore()
    store.load(mode)
    return execute(plan_commands(target, source, skills), mode, store)


def _make_skill(skills_dir: pathlib.Path, name: str, description: str = "desc") -> None:
    d = skills_dir / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\nBody.\n")


def _make_command(commands_dir: pathlib.Path, name: str) -> None:
    commands_dir.mkdir(parents=True)
    (commands_dir / f"{name}.md").write_text(f"---\ndescription: {name} cmd\n---\nRun {name}.\n")


def test_copies_real_commands(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "commands"
    _make_command(source, "foo")
    target = tmp_path / "config" / "opencode" / "commands"
    skills = tmp_path / "claude" / "skills"

    outcomes = apply_commands(target, source, skills, Mode.APPLY)

    assert (target / "foo.md").is_file()
    assert (target / "foo.md").read_text() == (source / "foo.md").read_text()


def test_generates_skill_command_stubs(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "commands"
    source.mkdir(parents=True)
    skills = tmp_path / "claude" / "skills"
    _make_skill(skills, "grill-me", "Interview me about a plan")
    target = tmp_path / "config" / "opencode" / "commands"

    outcomes = apply_commands(target, source, skills, Mode.APPLY)

    stub = target / "grill-me.md"
    assert stub.is_file()
    content = stub.read_text()
    assert "Interview me about a plan" in content
    assert "grill-me" in content


def test_skill_stub_includes_arguments_placeholder(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "commands"
    source.mkdir(parents=True)
    skills = tmp_path / "claude" / "skills"
    _make_skill(skills, "grill-me", "desc")
    target = tmp_path / "config" / "opencode" / "commands"

    apply_commands(target, source, skills, Mode.APPLY)

    assert "$ARGUMENTS" in (target / "grill-me.md").read_text()


def test_unknown_file_preserved_with_force(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "commands"
    source.mkdir(parents=True)
    skills = tmp_path / "claude" / "skills"
    target = tmp_path / "config" / "opencode" / "commands"
    target.mkdir(parents=True)
    (target / "stale.md").write_text("old")

    outcomes = apply_commands(target, source, skills, Mode.FORCE)

    assert (target / "stale.md").read_text() == "old"
    assert all(o.path.name != "stale.md" for o in outcomes)


def test_modified_managed_orphan_preserved(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "commands"
    source.mkdir(parents=True)
    skills = tmp_path / "claude" / "skills"
    target = tmp_path / "config" / "opencode" / "commands"
    target.mkdir(parents=True)
    (source / "stale.md").write_text("shared")
    apply_commands(target, source, skills, Mode.APPLY)
    (source / "stale.md").unlink()
    (target / "stale.md").write_text("old")

    outcomes = apply_commands(target, source, skills, Mode.APPLY)

    stale = next(o for o in outcomes if o.path.name == "stale.md")
    assert stale.status == Status.WARNED
    assert (target / "stale.md").read_text() == "old"


def test_dry_run_writes_nothing(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "commands"
    source.mkdir(parents=True)
    skills = tmp_path / "claude" / "skills"
    _make_skill(skills, "grill-me", "desc")
    target = tmp_path / "config" / "opencode" / "commands"

    outcomes = apply_commands(target, source, skills, Mode.DRY_RUN)

    assert not target.exists() or not any(target.iterdir())


def test_real_command_not_overwritten_by_skill_stub(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "commands"
    _make_command(source, "shared")
    skills = tmp_path / "claude" / "skills"
    _make_skill(skills, "shared", "skill desc")
    target = tmp_path / "config" / "opencode" / "commands"

    outcomes = apply_commands(target, source, skills, Mode.APPLY)

    assert (target / "shared.md").read_text() == (source / "shared.md").read_text()


@pytest.mark.parametrize("description", [
    "Use when: x", '"quoted" start', "'single' start", "- leading dash", "# leading hash",
    "[bracket", "{brace", "ends with colon:", "a: b # c", "line one\nline two",
])
def test_skill_stub_frontmatter_round_trips(tmp_path: pathlib.Path, description: str) -> None:
    import json

    import yaml

    skills = tmp_path / "claude" / "skills"
    skill = skills / "grill-me"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\n"
        "name: grill-me\n"
        f"description: {json.dumps(description)}\n"
        "---\nBody.\n"
    )
    target = tmp_path / "config" / "opencode" / "commands"
    (tmp_path / "claude" / "commands").mkdir(parents=True)
    apply_commands(target, tmp_path / "claude" / "commands", skills, Mode.APPLY)
    stub = (target / "grill-me.md").read_text()
    frontmatter_text = stub.split("---\n")[1]
    assert yaml.safe_load(frontmatter_text)["description"] == description
    assert "$ARGUMENTS" in stub
