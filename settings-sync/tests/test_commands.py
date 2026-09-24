import pathlib

import pytest

from settings_sync.commands import sync_commands
from settings_sync.sync import Status


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

    outcomes = sync_commands(target, source, skills)

    assert (target / "foo.md").is_file()
    assert (target / "foo.md").read_text() == (source / "foo.md").read_text()


def test_generates_skill_command_stubs(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "commands"
    source.mkdir(parents=True)
    skills = tmp_path / "claude" / "skills"
    _make_skill(skills, "grill-me", "Interview me about a plan")
    target = tmp_path / "config" / "opencode" / "commands"

    outcomes = sync_commands(target, source, skills)

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

    sync_commands(target, source, skills)

    assert "$ARGUMENTS" in (target / "grill-me.md").read_text()


def test_unknown_file_preserved_with_force(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "commands"
    source.mkdir(parents=True)
    skills = tmp_path / "claude" / "skills"
    target = tmp_path / "config" / "opencode" / "commands"
    target.mkdir(parents=True)
    (target / "stale.md").write_text("old")

    outcomes = sync_commands(target, source, skills, force=True)

    assert (target / "stale.md").read_text() == "old"


def test_modified_managed_orphan_preserved(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "commands"
    source.mkdir(parents=True)
    skills = tmp_path / "claude" / "skills"
    target = tmp_path / "config" / "opencode" / "commands"
    target.mkdir(parents=True)
    (source / "stale.md").write_text("shared")
    sync_commands(target, source, skills)
    (source / "stale.md").unlink()
    (target / "stale.md").write_text("old")

    outcomes = sync_commands(target, source, skills)

    stale = next(o for o in outcomes if o.path.name == "stale.md")
    assert stale.status == Status.WARNED
    assert (target / "stale.md").read_text() == "old"


def test_dry_run_writes_nothing(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "commands"
    source.mkdir(parents=True)
    skills = tmp_path / "claude" / "skills"
    _make_skill(skills, "grill-me", "desc")
    target = tmp_path / "config" / "opencode" / "commands"

    outcomes = sync_commands(target, source, skills, dry_run=True)

    assert not target.exists() or not any(target.iterdir())


def test_real_command_not_overwritten_by_skill_stub(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "commands"
    _make_command(source, "shared")
    skills = tmp_path / "claude" / "skills"
    _make_skill(skills, "shared", "skill desc")
    target = tmp_path / "config" / "opencode" / "commands"

    outcomes = sync_commands(target, source, skills)

    assert (target / "shared.md").read_text() == (source / "shared.md").read_text()
