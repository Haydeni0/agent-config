import pathlib

import pytest

from settings_sync.agents_md import sync_agents_md
from settings_sync.actions import Status


def test_sync_appends_rules_md_when_present(tmp_path: pathlib.Path):
    claude = tmp_path / "claude" / "CLAUDE.md"
    claude.parent.mkdir(parents=True)
    claude.write_text("# Guidelines\nMain content.\n")
    rules = tmp_path / "claude" / "opencode" / "rules.md"
    rules.parent.mkdir(parents=True)
    rules.write_text("# opencode rules\nNo sudo.\n")
    target = tmp_path / "config" / "opencode" / "AGENTS.md"

    sync_agents_md(target, claude, rules_path=rules)

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

    sync_agents_md(target, claude, rules_path=rules)

    content = target.read_text()
    assert "Main content." in content
    assert "No sudo." not in content
