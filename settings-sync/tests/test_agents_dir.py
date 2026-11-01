import pathlib

import pytest

from settings_sync.agents import plan_agents_dir
from settings_sync.actions import Mode, Status
from settings_sync.executor import execute
from settings_sync.frontmatter import parse
from settings_sync.ownership import OwnershipStore

AGENT_A = """---
name: reviewer
description: reviews
tools: Read, Grep
---

Body A.
"""


def apply_agents_dir(target: pathlib.Path, source: pathlib.Path, mode: Mode):
    store = OwnershipStore()
    store.load(mode)
    return execute(plan_agents_dir(target, source), mode, store)


def test_transforms_and_writes_all_source_agents(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "agents"
    source.mkdir(parents=True)
    (source / "reviewer.md").write_text(AGENT_A)
    (source / "auditor.md").write_text(AGENT_A.replace("reviewer", "auditor"))
    target = tmp_path / "config" / "opencode" / "agents"

    outcomes = apply_agents_dir(target, source, Mode.APPLY)

    assert (target / "reviewer.md").is_file()
    assert (target / "auditor.md").is_file()
    fm, _ = parse((target / "reviewer.md").read_text())
    assert "permission" in fm


@pytest.mark.parametrize("force", [False, True])
def test_unknown_target_preserved(tmp_path: pathlib.Path, force: bool):
    source = tmp_path / "claude" / "agents"
    source.mkdir(parents=True)
    (source / "reviewer.md").write_text(AGENT_A)
    target = tmp_path / "config" / "opencode" / "agents"
    target.mkdir(parents=True)
    (target / "orphan.md").write_text("stale")

    outcomes = apply_agents_dir(target, source, Mode.FORCE if force else Mode.APPLY)

    assert all(o.path.name != "orphan.md" for o in outcomes)
    assert (target / "orphan.md").read_text() == "stale"


def test_managed_orphan_removed(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "agents"
    source.mkdir(parents=True)
    (source / "reviewer.md").write_text(AGENT_A)
    target = tmp_path / "config" / "opencode" / "agents"
    target.mkdir(parents=True)
    (source / "orphan.md").write_text(AGENT_A)
    apply_agents_dir(target, source, Mode.APPLY)
    (source / "orphan.md").unlink()

    outcomes = apply_agents_dir(target, source, Mode.APPLY)

    orphan = next(o for o in outcomes if o.path.name == "orphan.md")
    assert orphan.status == Status.REPLACED
    assert not (target / "orphan.md").exists()


def test_dry_run_writes_nothing(tmp_path: pathlib.Path):
    source = tmp_path / "claude" / "agents"
    source.mkdir(parents=True)
    (source / "reviewer.md").write_text(AGENT_A)
    target = tmp_path / "config" / "opencode" / "agents"

    outcomes = apply_agents_dir(target, source, Mode.DRY_RUN)

    assert not any(target.iterdir()) if target.exists() else True
    reviewer = next(o for o in outcomes if o.path.name == "reviewer.md")
    assert reviewer.status == Status.WOULD_CREATE
