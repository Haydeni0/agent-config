import pathlib

import pytest

from settings_sync.agents_md import plan_agents_md
from settings_sync.actions import Mode, Status
from settings_sync.executor import execute
from settings_sync.ownership import OwnershipStore


def _apply(target: pathlib.Path, claude: pathlib.Path, rules: pathlib.Path) -> None:
    store = OwnershipStore()
    store.load(Mode.APPLY)
    execute(plan_agents_md(target, claude, rules_path=rules), Mode.APPLY, store)


def test_sync_appends_rules_md_when_present(tmp_path: pathlib.Path):
    claude = tmp_path / "claude" / "CLAUDE.md"
    claude.parent.mkdir(parents=True)
    claude.write_text("# Guidelines\nMain content.\n")
    rules = tmp_path / "claude" / "opencode" / "rules.md"
    rules.parent.mkdir(parents=True)
    rules.write_text("# opencode rules\nNo sudo.\n")
    target = tmp_path / "config" / "opencode" / "AGENTS.md"

    _apply(target, claude, rules)

    content = target.read_text()
    assert "Main content." in content
    assert "No sudo." in content
    assert content.index("Main content.") < content.index("No sudo.")


def test_sync_omits_rules_when_no_rules_file(tmp_path: pathlib.Path):
    claude = tmp_path / "claude" / "CLAUDE.md"
    claude.parent.mkdir(parents=True)
    claude.write_text("# Guidelines\nMain content.\n")
    rules = tmp_path / "claude" / "opencode" / "rules.md"
    target = tmp_path / "config" / "opencode" / "AGENTS.md"

    _apply(target, claude, rules)

    content = target.read_text()
    assert "Main content." in content
    assert "No sudo." not in content
