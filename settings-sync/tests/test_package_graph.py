"""Tests for skills/work-package/graph.py: dependency edges and frontier
(scenarios T1-T9, F1-F4, I1; REQ-SKILLS-14 graph amendment, REQ-SKILLS-26)."""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GRAPH = REPO_ROOT / "skills" / "work-package" / "graph.py"


@pytest.fixture(scope="module")
def graph() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("wp_graph", GRAPH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["wp_graph"] = module
    spec.loader.exec_module(module)
    return module


def make_pkg(tmp_path: Path, plan: str = "", decisions: str = "") -> Path:
    make_pkg.n += 1
    pkg = tmp_path / f"pkg{make_pkg.n}"
    pkg.mkdir()
    if plan:
        (pkg / "plan.md").write_text(plan + "\n")
    if decisions:
        (pkg / "decisions.md").write_text(decisions + "\n")
    return pkg


make_pkg.n = 0


def check(graph: types.ModuleType, tmp_path: Path, plan: str = "", decisions: str = "") -> list[str]:
    return graph.check_pkg(make_pkg(tmp_path, plan, decisions))


def test_t1_dangling_task_ref(graph: types.ModuleType, tmp_path: Path):
    findings = check(graph, tmp_path, plan=(
        "### Task 1: A\n**Blocked by:** Task 9\n- [ ] step\n"
    ))
    assert any("Task 9" in f for f in findings)


def test_t2_cycles(graph: types.ModuleType, tmp_path: Path):
    plan = (
        "### Task 1: A\n**Blocked by:** Task 2\n- [ ] s\n"
        "### Task 2: B\n**Blocked by:** Task 1\n- [ ] s\n"
    )
    assert any("cycle" in f.lower() for f in check(graph, tmp_path, plan=plan))
    self_loop = "### Task 1: A\n**Blocked by:** Task 1\n- [ ] s\n"
    assert any("cycle" in f.lower() for f in check(graph, tmp_path, plan=self_loop))


def test_t3_closed_task_with_open_blocker(graph: types.ModuleType, tmp_path: Path):
    plan = (
        "### Task 1: A\n**Blocked by:** None\n- [x] s\n"
        "### Task 2: B\n**Blocked by:** Task 3\n- [x] s\n"
        "### Task 3: C\n**Blocked by:** None\n- [ ] s\n"
    )
    findings = check(graph, tmp_path, plan=plan)
    assert any("Task 2" in f and "Task 3" in f for f in findings)


def test_t4_partial_opt_in_and_zero_boxes(graph: types.ModuleType, tmp_path: Path):
    partial = (
        "### Task 1: A\n**Blocked by:** None\n- [ ] s\n"
        "### Task 2: B\n- [ ] s\n"
    )
    assert any("Task 2" in f and "Blocked by" in f for f in check(graph, tmp_path, plan=partial))
    zero = (
        "### Task 1: A\n**Blocked by:** None\n- [ ] s\n"
        "### Task 2: B\n**Blocked by:** Task 1\n"
    )
    assert any("Task 2" in f and "checkbox" in f for f in check(graph, tmp_path, plan=zero))


def test_t4b_legacy_plan_passes(graph: types.ModuleType, tmp_path: Path):
    plan = "### Task 1: A\n- [ ] s\n### Task 2: B\n- [x] s\n"
    assert check(graph, tmp_path, plan=plan) == []


def test_t9_duplicate_task_id(graph: types.ModuleType, tmp_path: Path):
    plan = (
        "### Task 1: A\n**Blocked by:** None\n- [ ] s\n"
        "### Task 1: B\n**Blocked by:** None\n- [ ] s\n"
    )
    assert any("duplicate" in f.lower() for f in check(graph, tmp_path, plan=plan))


def test_t8_cross_file_ref_in_plan(graph: types.ModuleType, tmp_path: Path):
    plan = "### Task 1: A\n**Blocked by:** Q1\n- [ ] s\n"
    assert any("cross" in f.lower() for f in check(graph, tmp_path, plan=plan))


def test_unparseable_ref_is_finding(graph: types.ModuleType, tmp_path: Path):
    plan = "### Task 1: A\n**Blocked by:** Taskk 2\n- [ ] s\n"
    assert any("Taskk 2" in f for f in check(graph, tmp_path, plan=plan))


def test_fenced_content_ignored(graph: types.ModuleType, tmp_path: Path):
    plan = (
        "### Task 1: A\n**Blocked by:** None\n- [ ] s\n"
        "```markdown\n### Task 2: fake\n**Blocked by:** Task 99\n```\n"
    )
    assert check(graph, tmp_path, plan=plan) == []


def test_t5_dangling_q_ref(graph: types.ModuleType, tmp_path: Path):
    decisions = (
        "state: grill\n\n## Open questions\n\n- Q1. First? Blocked by: Q7\n"
    )
    assert any("Q7" in f for f in check(graph, tmp_path, decisions=decisions))


def test_t5b_resolves_citation_closes(graph: types.ModuleType, tmp_path: Path):
    decisions = (
        "state: grill\n\n## Decisions\n\n- D1. **X.** Resolves Q7.\n\n"
        "## Open questions\n\n- Q1. First? Blocked by: Q7\n"
    )
    assert check(graph, tmp_path, decisions=decisions) == []


def test_t6_struck_q_closes(graph: types.ModuleType, tmp_path: Path):
    decisions = (
        "state: grill\n\n## Open questions\n\n"
        "- Q1. First? Blocked by: Q2\n- ~~Q2. Old?~~ Superseded.\n"
    )
    assert check(graph, tmp_path, decisions=decisions) == []


def test_t7_q_tags(graph: types.ModuleType, tmp_path: Path):
    bad = "state: grill\n\n## Open questions\n\n- Q1 [spike]. First?\n"
    assert any("spike" in f for f in check(graph, tmp_path, decisions=bad))
    good = "state: grill\n\n## Open questions\n\n- Q1 [research]. First?\n- Q2. Second?\n"
    assert check(graph, tmp_path, decisions=good) == []


def test_t9_duplicate_q_id(graph: types.ModuleType, tmp_path: Path):
    decisions = (
        "state: grill\n\n## Open questions\n\n- Q1. A?\n- Q1. B?\n"
    )
    assert any("duplicate" in f.lower() for f in check(graph, tmp_path, decisions=decisions))


def test_cross_file_ref_in_decisions(graph: types.ModuleType, tmp_path: Path):
    decisions = "state: grill\n\n## Open questions\n\n- Q1. A? Blocked by: Task 2\n"
    assert any("cross" in f.lower() for f in check(graph, tmp_path, decisions=decisions))


def test_q_cycle(graph: types.ModuleType, tmp_path: Path):
    decisions = (
        "state: grill\n\n## Open questions\n\n"
        "- Q1. A? Blocked by: Q2\n- Q2. B? Blocked by: Q1\n"
    )
    assert any("cycle" in f.lower() for f in check(graph, tmp_path, decisions=decisions))


def test_q_title_excludes_blocked_by_text(graph: types.ModuleType, tmp_path: Path):
    qs, resolved = graph.parse_decisions(
        "## Open questions\n\n- Q1. What is it? Blocked by: Q2\n- Q2. B?\n"
    )
    assert qs[0].title == "What is it?"
    assert qs[0].blocked_by == ["Q2"]


def test_f1_frontier_order_and_task_type_null(graph: types.ModuleType, tmp_path: Path):
    plan = (
        "### Task 1: A\n**Blocked by:** None\n- [x] s\n"
        "### Task 2: B\n**Blocked by:** Task 1\n- [ ] s\n"
        "### Task 3: C\n**Blocked by:** Task 2\n- [ ] s\n"
        "### Task 4: D\n**Blocked by:** None\n- [ ] s\n"
    )
    items = graph.frontier_pkg(make_pkg(tmp_path, plan=plan))
    assert [i["id"] for i in items] == ["Task 2", "Task 4"]
    assert all(i["type"] is None and i["kind"] == "task" for i in items)
    assert items[0]["blocked_by"] == ["Task 1"]
    assert items[0]["title"] == "B"


def test_f2_frontier_q_fields(graph: types.ModuleType, tmp_path: Path):
    decisions = (
        "state: grill\n\n## Decisions\n\n- D1. **X.** Resolves Q7.\n\n"
        "## Open questions\n\n- Q4. What next? Blocked by: Q7\n- Q9. Untagged?\n"
    )
    items = graph.frontier_pkg(make_pkg(tmp_path, decisions=decisions))
    by_id = {i["id"]: i for i in items}
    assert by_id["Q4"]["type"] == "grill" and by_id["Q4"]["kind"] == "q"
    assert by_id["Q9"]["type"] == "grill"
    assert all(set(i) == {"id", "kind", "type", "title", "blocked_by"} for i in items)


def test_f3_cli_frontier_finds_no_array(graph: types.ModuleType, tmp_path: Path):
    from typer.testing import CliRunner
    runner = CliRunner()
    pkg = make_pkg(tmp_path, plan="### Task 1: A\n**Blocked by:** Task 9\n- [ ] s\n")
    result = runner.invoke(graph.app, ["frontier", str(pkg)])
    assert result.exit_code != 0
    assert result.stdout.strip() == ""


def test_f4_cli_frontier_json(graph: types.ModuleType, tmp_path: Path):
    from typer.testing import CliRunner
    runner = CliRunner()
    plan = (
        "### Task 1: A\n**Blocked by:** None\n- [x] s\n"
        "### Task 2: B\n**Blocked by:** Task 1\n- [ ] s\n"
    )
    result = runner.invoke(graph.app, ["frontier", str(make_pkg(tmp_path, plan=plan))])
    assert result.exit_code == 0
    items = json.loads(result.stdout)
    assert items[0]["id"] == "Task 2"


def test_typed_q_in_frontier(graph: types.ModuleType, tmp_path: Path):
    decisions = (
        "state: grill\n\n## Open questions\n\n- Q1 [research]. External fact? Blocked by: Q9\n"
        "- Q2 [prototype]. How should it look?\n- ~~Q9. Old?~~ Done.\n"
    )
    items = graph.frontier_pkg(make_pkg(tmp_path, decisions=decisions))
    by_id = {i["id"]: i for i in items}
    assert by_id["Q1"]["type"] == "research"
    assert by_id["Q2"]["type"] == "prototype"


def test_frontier_title_first_sentence(graph: types.ModuleType, tmp_path: Path):
    decisions = "state: grill\n\n## Open questions\n\n- Q1. How does X work? More context here.\n"
    items = graph.frontier_pkg(make_pkg(tmp_path, decisions=decisions))
    assert items[0]["title"] == "How does X work?"


def test_trailing_section_checkboxes_do_not_reopen_task(graph, tmp_path):
    plan = (
        "### Task 1: A\n**Blocked by:** None\n- [x] s\n"
        "## Notes\n- [ ] leftover idea\n"
    )
    assert graph.frontier_pkg(make_pkg(tmp_path, plan=plan)) == []


def test_second_blocked_by_line_is_finding(graph, tmp_path):
    plan = "### Task 1: A\n**Blocked by:** None\n**Blocked by:** Task 2\n- [ ] s\n"
    findings = check(graph, tmp_path, plan=plan)
    assert any("more than one Blocked by" in f for f in findings)


def test_blocked_by_outside_task_is_finding(graph, tmp_path):
    plan = "## Preamble\n**Blocked by:** None\n### Task 1: A\n**Blocked by:** None\n- [ ] s\n"
    findings = check(graph, tmp_path, plan=plan)
    assert any("outside any task" in f for f in findings)


def test_q_duplication_from_other_sections_not_flagged(graph, tmp_path):
    decisions = (
        "state: grill\n\n## Open questions\n\n- Q1. Real?\n\n"
        "## Review findings\n\n- Q1 mention inside a finding\n"
    )
    assert check(graph, tmp_path, decisions=decisions) == []


def test_resolves_only_counts_on_d_entries(graph, tmp_path):
    decisions = (
        "state: grill\n\n## Open questions\n\n- Q1. A? Blocked by: Q5\n\n"
        "## Review nits\n\n- nit: Resolves Q5 was mentioned in chat\n"
    )
    assert any("Q5" in f for f in check(graph, tmp_path, decisions=decisions))


def test_frontier_tasks_then_qs(graph, tmp_path):
    plan = (
        "### Task 1: A\n**Blocked by:** None\n- [ ] s\n"
        "### Task 2: B\n**Blocked by:** Task 1\n- [ ] s\n"
    )
    decisions = "state: grill\n\n## Open questions\n\n- Q1. First?\n- Q2. Second? Blocked by: Q1\n"
    items = graph.frontier_pkg(make_pkg(tmp_path, plan=plan, decisions=decisions))
    assert [i["id"] for i in items] == ["Task 1", "Q1"]


# S15 real-corpus fixtures: verbatim task blocks from the two real packages
# that carry lettered step labels (mailbox-receiver-cli Task 8; settings-sync
# engine Task 16), frozen here because the package store is machine-local.
MAILBOX_TASK8 = '''### Task 8: mailbox-overseer reply-conventions probe (D7, conditional edit)

**Files:**
- Modify (only on RED): `skills/mailbox-overseer/SKILL.md` - the Working loop **Brief** bullet's standing-answers list
- Modify: `.agents/work/2026-10-14-mailbox-receiver-cli/decisions.md` - record the probe outcome

- [x] **Step 1: Baseline probe (fresh subagent)**

Dispatch one fresh `general-purpose` subagent with no other context and this prompt:

```text
Read /mnt/home/hayden.dorahy/gitrepos/agent-config/skills/mailbox-overseer/SKILL.md and act as the overseer it describes. The worker is already joined to the mesh. The user just told you: "Have the worker port the CSV exporter to the new storage API. I might want to change the output columns once I see a sample - I'll tell you." Write the exact body of the first brief you would send with `mailbox send`. Do not run any commands; output only the brief body.
```

RED if the brief never says what silence means for the possible column change (e.g. "no message from me means no change - proceed"). GREEN if it does.

- [x] **Step 2a: On GREEN** - append under `## Outcome` in `decisions.md`: `D7 probe (2026-10-14): baseline brief stated what silence means unprompted; no mailbox-overseer edit (Iron Law).` Skip to Step 4.

- [ ] **Step 2b: On RED** - in `skills/mailbox-overseer/SKILL.md`, in the Brief bullet, change:

```markdown
  front-loads standing answers (scope, conventions, git gates,
  isolation - which units get worktrees and which share the tree with
  disjoint outputs, and which package paths units may write - anything
  the worker's grill would ask).
```

to:

```markdown
  front-loads standing answers (scope, conventions, git gates,
  isolation - which units get worktrees and which share the tree with
  disjoint outputs, and which package paths units may write - what
  silence means for any correction you might still send, e.g. "no
  message means no change, proceed" - anything the worker's grill
  would ask).
```

- [ ] **Step 3: On RED - GREEN probe**

Re-run the Step 1 prompt in a new fresh subagent. Expected: the brief now states what silence means. If it still does not, stop and report. Do not iterate wording beyond one revision without the user. Record both probe results under `## Outcome` in `decisions.md`.

- [ ] **Step 4: Commit (only if the skill changed)**

```bash
git add skills/mailbox-overseer/SKILL.md
printenv COMMIT_AUTHORISED && git commit -m "docs(mailbox-overseer): brief states what silence means" -- skills/mailbox-overseer/SKILL.md
```

---
'''

ENGINE_TASK16 = '''### Task 16: Contract - delete the old machinery; force matrices; retirement E2E

**Files:**
- Delete: `settings-sync/settings_sync/sync.py`
- Modify: `settings-sync/settings_sync/ownership.py` (delete `sync_generated_text`, `sync_generated_file`, `sync_generated_json`, `sync_generated_symlink`, `prune_generated`, the interim `entries()` view), `merging.py` (delete `install_merged`, `sync_json_defaults`, `sync_yaml_defaults`, `merge_defaults` moves behind the executor's declared-key merge), `registry.py` (delete `Step.run`, `run_harness`, `run_all_tools`; `ManagedEntry` cleanup if the `kind` remnant survives)
- Modify: `settings-sync/settings_sync/executor.py` (imports `write_text_atomic` from the new `fsutil.py`; drops the `sync` import)
- Modify: `settings-sync/tests/test_write_safety.py` (S61/S62 rewrites onto executor actions), `test_registry.py` (delete `test_all_skips_omitted_destinations`), `test_force.py` (S26/S27 matrices), `test_read_only.py` (S71 in-process), `test_adoption.py` (S32: pin the `failed` status)
- Modify: `settings-sync/README.md` (the `~/.agents/skills` force wording, D18)

**Interfaces:**
- Consumes: Tasks 13-15 (no step uses the old machinery).
- Produces: the module layout the spec's table names - `sync.py` gone (`write_text_atomic` lives in a new `fsutil.py` imported by `executor.py` and `ownership.py`; `install_text` is deleted outright - after Step 3 no caller remains, the executor's `_atomic_write` superseded it and `merging.install_merged` died with the old helpers), `ownership.py` is store-only, `merging.py` is codecs + merge helpers, `registry.py` declares `Step(name, plan, required_sources)` only.

**Blocked by:** Task 15

- [x] **Step 1: Write the failing tests**

S26/S27 in `settings-sync/tests/test_force.py` (the R2 proof; one parametrization per matrix; every conflict-capable step appears):

```python
import pytest
from typer.testing import CliRunner

from settings_sync.cli import agent_config_app


def _edited(path: Path, content: str) -> None:
    """Replace a managed file or link with edited local content - never write through a link."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


FILE_LINK_STEPS = [
    ("claude", "context", ".claude/CLAUDE.md"),
    ("claude", "links", ".claude/skills/uv"),
    ("opencode", "resources", ".config/opencode/skills/uv"),
    ("opencode", "agents-md", ".config/opencode/AGENTS.md"),
    ("opencode", "agents", ".config/opencode/agents/reviewer.md"),
    ("opencode", "commands", ".config/opencode/commands/foo.md"),
    ("opencode", "plugins", ".config/opencode/plugins/shared.js"),
    ("pi", "resources", ".pi/agent/skills/uv"),
    ("pi", "context", ".pi/agent/CLAUDE.md"),
    ("pi", "keybindings", ".pi/agent/keybindings.json"),
    ("goose", "resources", ".config/goose/skills/uv"),
    ("goose", "hints", ".config/goose/.goosehints"),
    ("goose", "providers", ".config/goose/custom_providers/glm.json"),
    ("goose", "hooks", ".agents/plugins/agent-config-goose/plugin.json"),
    ("agy", "agents-md", ".gemini/config/AGENTS.md"),
    ("agy", "skills", ".gemini/config/skills/uv"),
    ("codex", "agents-md", ".codex/AGENTS.md"),
    ("codex", "skills", ".agents/skills"),
    ("codegraph", "binary", ".local/bin/codegraph"),
]


def _seed(source_home: Path, harness: str, step: str) -> None:
    (source_home / "skills/uv/SKILL.md").write_text("---\nname: uv\ndescription: d\n---\nBody\n")
    (source_home / "commands/foo.md").write_text("---\ndescription: foo\n---\nRun foo.\n")
    (source_home / "agents/reviewer.md").write_text("---\nname: reviewer\ndescription: r\ntools: Read\n---\nBody.\n")
    (source_home / "harnesses/opencode/plugins/shared.js").write_text("// plugin")
    (source_home / "harnesses/goose/custom_providers/glm.json").write_text('{"name": "glm"}')
    (source_home / "harnesses/gemini/settings.json").write_text('{"model": "gemini"}')
    (source_home / "harnesses/claude/settings.json").write_text('{"permissions": {"allow": []}}')


@pytest.mark.parametrize("harness,step,target", FILE_LINK_STEPS)
def test_conflict_without_force_is_skipped(source_home: Path, isolated_home: Path, harness: str, step: str, target: str):
    _seed(source_home, harness, step)
    args = ["--source", str(source_home)]
    runner = CliRunner()
    assert runner.invoke(agent_config_app, [*args, "sync", harness]).exit_code == 0, harness
    _edited(isolated_home / target, "hand edited\n")
    result = runner.invoke(agent_config_app, [*args, "sync", harness, step])
    assert result.exit_code == 1, result.output
    assert "skipped" in result.output
    assert (isolated_home / target).read_text() in ("hand edited\n", "hand edited") or (isolated_home / target).is_symlink()


@pytest.mark.parametrize("harness,step,target", FILE_LINK_STEPS)
def test_force_resolves_every_conflict(source_home: Path, isolated_home: Path, harness: str, step: str, target: str):
    _seed(source_home, harness, step)
    args = ["--source", str(source_home)]
    runner = CliRunner()
    assert runner.invoke(agent_config_app, [*args, "sync", harness]).exit_code == 0, harness
    _edited(isolated_home / target, "hand edited\n")
    result = runner.invoke(agent_config_app, [*args, "sync", harness, step, "--force"])
    assert result.exit_code == 0, result.output
    assert "skipped" not in result.output
    backups = isolated_home / ".local/state/agent-config/backups"
    assert any(p.is_file() for p in backups.rglob("*")), (harness, step)
```

Caveats the implementer must respect (do not weaken the scenarios): the claude `links`, opencode/pi/goose `resources`, agy `skills`, and codex `skills` targets are symlinks - `_edited` replaces the link with a real file (that is the foreign-entry conflict); the `goose hooks` row targets the plugin manifest (`plugin.json`, a File action), because the hooks target itself is a hook-bearing `MergedConfig`: a plain-text edit there fails group reconciliation (`failed`, force-immune) and a valid-JSON foreign-group edit merges with exit 0 - neither is a `skipped` conflict; the `codegraph binary` target is the launcher symlink - `_edited` replaces it with a foreign file. No param edits a directory and every force-resolved conflict replaces a file or link, so the single unconditional backup assertion covers all of them - no `or`-style exception, no split parametrize. If a param's first whole-harness sync cannot exit 0 (e.g. lint warnings from an unrelated broken skill - there are none in `source_home`), fix the seed, not the assertion.

- [x] **Step 1b: Rewrite `test_config_ownership.py` off `sync_json_defaults` (before the deletion in Step 3)**

The module imports `sync_json_defaults` at module level and Task 16's Step 3 deletes it, so rewrite first:

- Delete `test_removed_template_key_retained_and_arrays_replace` (superseded by Task 17's `test_key_ownership.py::test_declared_arrays_and_scalars_replace`, REQ-SYNC-13) and `test_native_edit_during_merge_preserved` (superseded by `tests/test_executor.py::test_native_edit_during_merge_preserved`, seam B).
- Keep `test_invalid_mapping_preserves_target` untouched (CLI-level, contract-cited, green throughout).
- Rewrite the contract-cited `test_declared_null_is_installed` onto the plan/execute seam (same file, same name):

```python
def test_declared_null_is_installed(isolated_home: Path) -> None:
    from settings_sync.actions import MergedConfig, Mode
    from settings_sync.executor import execute
    from settings_sync.merging import JsonCodec
    from settings_sync.ownership import OwnershipStore

    target = isolated_home / "settings.json"
    store = OwnershipStore()
    store.load(Mode.APPLY)
    execute([MergedConfig(target, JsonCodec(), {"explicit_null": None})], Mode.APPLY, store)
    assert json.loads(target.read_text()) == {"explicit_null": None}
```

- Drop the `from settings_sync.merging import sync_json_defaults` import line.

Run: `cd settings-sync && uv run --locked pytest tests/test_config_ownership.py -q`
Expected: PASS

S61/S62 final forms: `tests/test_executor.py` already carries both from Task 12 (`test_failed_replace_preserves_original` over the three builders below, `test_regular_output_rejects_symlink` over File/MergedConfig/Regenerate), so `test_write_safety.py` keeps only its CLI jsonc cases from Task 14 plus one re-pointed link test. In `test_write_safety.py`, delete the interim `sync_yaml`-based `test_failed_replace_preserves_original` and `test_regular_output_rejects_symlink` (superseded by the executor tests) and re-point `test_symlink_replace_failure_preserves_old_link` (same name, same file):

```python
def test_symlink_replace_failure_preserves_old_link(isolated_home: Path, mocker: MockerFixture) -> None:
    from settings_sync.actions import Mode, Symlink
    from settings_sync.executor import execute
    from settings_sync.ownership import OwnershipStore

    old = isolated_home / "old"
    old.mkdir()
    new = isolated_home / "new"
    new.mkdir()
    target = isolated_home / "target"
    target.symlink_to(old)
    mocker.patch("pathlib.Path.replace", side_effect=OSError("disk unavailable"))
    store = OwnershipStore()
    store.load(Mode.FORCE)
    outcome = execute([Symlink(target, new)], Mode.FORCE, store)[0]
    assert outcome.status == Status.FAILED
    assert target.resolve() == old.resolve()
```

S71 in `test_read_only.py` - replace the subprocess loop with an in-process one (the autouse download stub then applies):

```python
def test_repository_checkout_sync_and_check(isolated_home: Path):
    from typer.testing import CliRunner
    from settings_sync.cli import agent_config_app
    source = Path(__file__).resolve().parents[2]
    sentinel = isolated_home / ".codex/sessions/preserved"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("local session")
    runner = CliRunner()
    args = ["--source", str(source)]
    for command in (["sync"], ["sync"], ["check"], ["doctor"]):
        result = runner.invoke(agent_config_app, [*args, *command])
        assert result.exit_code == 0, command, result.output
        assert sentinel.read_text() == "local session"
```

Delete `test_registry.py::test_all_skips_omitted_destinations` (its premise - a None destination skipping a harness - is gone: every destination resolves; the replacement coverage is S41's registry-driven surfaces and the CLI tests).

- [x] **Step 2: Run them to verify they fail**

Run: `cd settings-sync && uv run --locked pytest tests/test_force.py tests/test_write_safety.py tests/test_read_only.py -q`
Expected: the new matrix cases FAIL against any step that still ignores `--force` or any leftover old machinery; S71 fails until `sync.py` interop is gone only if the legacy subprocess form is still in place - it passes in-process already, so require the matrix failures.

- [x] **Step 3: Delete the old machinery**

- Move `write_text_atomic` from `sync.py` into a new `settings_sync/fsutil.py` imported by both `executor.py` and `ownership.py` (the spec's layout puts it in `executor.py`; the one-line `fsutil` indirection avoids the import cycle that `ownership -> executor` would create - document the deviation in the module docstring). Delete `install_text` with `sync.py`: no caller remains after this step.
- Delete `sync.py`; delete from `ownership.py`: `sync_generated_text`, `sync_generated_file`, `sync_generated_json`, `sync_generated_symlink`, `prune_generated`, `entries()` (the `record_file`/`record_symlink` pair landed in Task 11; the executor's `_record` already routes through it - no call-site changes here).
- Delete from `merging.py`: `install_merged`, `sync_json_defaults`, `sync_yaml_defaults`; keep `merge_defaults` (the executor's declared-key merge), codecs, `strip_jsonc`, `canonicalize`.
- `registry.py`: `Step` loses the `run` field; delete `run_harness`, `run_all_tools`; `Harness` keeps `name`, `steps`, `destination`, `host` (declaration fields arrive in Task 18).
- `test_write_safety.py`, `test_agents_dir.py`, `test_goose.py`, `test_agy.py`: any leftover `sync_dir_files`/`sync_yaml`/`sync_generated_*` imports are gone with the deleted tests from earlier tasks; `rg -n "settings_sync.sync|sync_generated|prune_generated|run_harness|run_all_tools" settings-sync/settings_sync settings-sync/tests` returns nothing.

- [x] **Step 3b: Pin S32's status flip in `test_adoption.py`**

In `test_foreign_shared_skill_collision_preserved`, add the D18 status assertion after the exit-code check:

```python
    assert result.exit_code == 1
    assert "failed" in result.output
    assert existing.read_text() == "personal"
```

(a real directory at a managed link path is `failed`, never `skipped` - it was already `failed` from Task 12's executor onward; this pins it against regression to the old `skipped`.)

- [x] **Step 4: README force wording (D18, X6)**

In `settings-sync/README.md`, replace the sentence "A foreign directory/link is reported and preserved, including with force." with: "A foreign link at `~/.agents/skills` is a normal conflict: `--force` backs it up and repoints it at the source `skills/`; a real directory there is preserved and reported as failed."

- [x] **Step 5: Slice 3 gate**

Run: `cd settings-sync && uv run --locked pytest -q` then `bash scripts/verify.sh`
Expected: both green; suite under 20s (check with `time`)

- [x] **Step 6: Commit**

```bash
git add -A settings-sync && git commit -m "refactor(settings-sync): delete legacy write paths; executor owns atomic writes"
```

---
'''


def _runner():
    from typer.testing import CliRunner

    return CliRunner()


def test_s13_tick_flips_only_target_task(graph: types.ModuleType, tmp_path: Path):
    plan = (
        "### Task 1: A\n**Blocked by:** None\n- [ ] step one\n- [ ] step two\n"
        "### Task 2: B\n**Blocked by:** None\n- [ ] other\n"
    )
    pkg = make_pkg(tmp_path, plan=plan)
    result = _runner().invoke(graph.app, ["tick", str(pkg), "1"])
    assert result.exit_code == 0, result.output
    text = (pkg / "plan.md").read_text()
    assert "- [x] step one" in text and "- [x] step two" in text
    assert "- [ ] other" in text


def test_s13_tick_rejects_re_tick(graph: types.ModuleType, tmp_path: Path):
    plan = "### Task 1: A\n**Blocked by:** None\n- [x] done\n"
    pkg = make_pkg(tmp_path, plan=plan)
    result = _runner().invoke(graph.app, ["tick", str(pkg), "1"])
    assert result.exit_code != 0
    assert (pkg / "plan.md").read_text() == plan + "\n"


def test_s13_tick_rejects_unknown_task(graph: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(tmp_path, plan="### Task 1: A\n**Blocked by:** None\n- [ ] s\n")
    result = _runner().invoke(graph.app, ["tick", str(pkg), "9"])
    assert result.exit_code != 0
    assert "9" in result.output


def test_s13_tick_rejects_duplicate_task_numbers(graph: types.ModuleType, tmp_path: Path):
    plan = (
        "### Task 1: A\n**Blocked by:** None\n- [ ] s\n"
        "### Task 1: B\n**Blocked by:** None\n- [ ] s\n"
        "### Task 2: C\n**Blocked by:** None\n- [ ] s\n"
    )
    pkg = make_pkg(tmp_path, plan=plan)
    before = (pkg / "plan.md").read_text()
    for target in ("1", "2"):
        result = _runner().invoke(graph.app, ["tick", str(pkg), target])
        assert result.exit_code != 0
        assert "duplicate" in result.output
    assert (pkg / "plan.md").read_text() == before


def test_s13_tick_rejects_task_without_checkboxes(graph: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(tmp_path, plan="### Task 1: A\n**Blocked by:** None\nprose only\n")
    result = _runner().invoke(graph.app, ["tick", str(pkg), "1"])
    assert result.exit_code != 0
    assert "checkbox" in result.output


def test_s13_tick_never_touches_fenced_lines(graph: types.ModuleType, tmp_path: Path):
    plan = (
        "### Task 1: A\n**Blocked by:** None\n- [ ] real box\n"
        "```markdown\n- [ ] fenced box\n```\n- [ ] another real\n"
    )
    pkg = make_pkg(tmp_path, plan=plan)
    result = _runner().invoke(graph.app, ["tick", str(pkg), "1"])
    assert result.exit_code == 0, result.output
    text = (pkg / "plan.md").read_text()
    assert "- [ ] fenced box" in text
    assert "- [x] real box" in text and "- [x] another real" in text


def test_s14_detect_reports_facts(graph: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(
        tmp_path,
        plan="### Task 1: A\n**Blocked by:** None\n- [x] s\n- [ ] t\n\nReviewed: fail 1\n",
        decisions=(
            "state: spec\n\n## Decisions\n\n- D1. **X.** Rejected: Y.\n\n"
            "## Open questions\n\n- Q1. Open?\n\n## Review findings\n\n1. HIGH broken\n"
        ),
    )
    (pkg / "spec.md").write_text("Spec body.\n\nReviewed: pass 1\n")
    (pkg / "scenarios.md").write_text("# Scenarios\n")
    result = _runner().invoke(graph.app, ["detect", str(pkg)])
    assert result.exit_code == 0, result.output
    facts = json.loads(result.stdout)
    assert set(facts) == {"state", "has_state_line", "outcome", "d_entries",
                          "open_qs", "review_findings", "spec", "plan", "scenarios"}
    assert facts["state"] == "spec" and facts["has_state_line"] is True
    assert facts["outcome"] is False
    assert facts["d_entries"] == 1
    assert facts["open_qs"] == 1
    assert facts["review_findings"] is True
    assert facts["spec"] == {"exists": True, "nonempty": True, "markers": ["pass 1"]}
    assert facts["plan"] == {"exists": True, "nonempty": True, "markers": ["fail 1"],
                            "implemented": False, "boxes": 2, "unchecked": 1,
                            "fully_checked": False}
    assert facts["scenarios"] == {"exists": True, "nonempty": True}


def test_s14_detect_outcome_implemented_and_empty_files(graph: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(
        tmp_path,
        plan="### Task 1: A\n**Blocked by:** None\n- [x] s\n\nReviewed: pass 2\nImplemented\n",
        decisions="state: complete\n\n## Outcome\n\nMet.\n",
    )
    (pkg / "spec.md").write_text("\n")  # empty-but-present
    result = _runner().invoke(graph.app, ["detect", str(pkg)])
    assert result.exit_code == 0, result.output
    facts = json.loads(result.stdout)
    assert facts["state"] == "complete"
    assert facts["outcome"] is True
    assert facts["d_entries"] == 0
    assert facts["open_qs"] == 0
    assert facts["review_findings"] is False
    assert facts["spec"] == {"exists": True, "nonempty": False, "markers": []}
    assert facts["plan"]["implemented"] is True
    assert facts["plan"]["fully_checked"] is True
    assert facts["plan"]["markers"] == ["pass 2"]
    assert facts["scenarios"] == {"exists": False, "nonempty": False}


def test_s14_detect_absent_state_line_is_legacy_fact(graph: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(tmp_path, decisions="## Decisions\n\n- D1. A.\n")
    result = _runner().invoke(graph.app, ["detect", str(pkg)])
    assert result.exit_code == 0, result.output
    facts = json.loads(result.stdout)
    assert facts["state"] is None and facts["has_state_line"] is False


def test_s14_detect_errors_on_malformed_state_line(graph: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(tmp_path, decisions="state: grill extra\n\n## Decisions\n")
    result = _runner().invoke(graph.app, ["detect", str(pkg)])
    assert result.exit_code != 0
    assert "malformed" in result.output


def test_s14_detect_errors_on_absent_decisions(graph: types.ModuleType, tmp_path: Path):
    pkg = make_pkg(tmp_path, plan="### Task 1: A\n**Blocked by:** None\n- [ ] s\n")
    result = _runner().invoke(graph.app, ["detect", str(pkg)])
    assert result.exit_code != 0
    assert "decisions.md" in result.output


def test_s16_duplicate_live_d_ids(graph: types.ModuleType, tmp_path: Path):
    two_live = "state: grill\n\n## Decisions\n\n- D1. **A.** Rejected: x.\n- D1. **B.** Rejected: y.\n"
    findings = check(graph, tmp_path, decisions=two_live)
    assert any("D1" in f and "duplicate" in f.lower() for f in findings)


def test_s16_live_plus_struck_d_id(graph: types.ModuleType, tmp_path: Path):
    live_plus_struck = (
        "state: grill\n\n## Decisions\n\n- D1. **A.** Rejected: x.\n"
        "- ~~D1 (2026-10-01). Old.~~ Superseded.\n"
    )
    findings = check(graph, tmp_path, decisions=live_plus_struck)
    assert any("D1" in f for f in findings)


def test_s16_struck_pairs_and_distinct_ids_clean(graph: types.ModuleType, tmp_path: Path):
    clean = (
        "state: grill\n\n## Decisions\n\n- D1. **A.** Rejected: x.\n"
        "- ~~D2 (2026-10-01). Old.~~ Superseded.\n- D3. **C.** Rejected: z.\n"
        "- ~~D4 (2026-10-01). Old.~~ X.\n- ~~D4 (2026-10-01). Older.~~ Y.\n"
    )
    assert check(graph, tmp_path, decisions=clean) == []


def test_s15_step_gap_is_finding(graph: types.ModuleType, tmp_path: Path):
    plan = (
        "### Task 3: A\n**Blocked by:** None\n"
        "- [ ] **Step 1: a**\n- [ ] **Step 2: b**\n- [ ] **Step 4: d**\n"
    )
    findings = check(graph, tmp_path, plan=plan)
    assert any("Task 3" in f and "expected Step 3" in f for f in findings)


def test_s15_steps_must_start_at_one(graph: types.ModuleType, tmp_path: Path):
    plan = "### Task 1: A\n**Blocked by:** None\n- [ ] **Step 2: b**\n- [ ] **Step 3: c**\n"
    findings = check(graph, tmp_path, plan=plan)
    assert any("start at 1" in f for f in findings)


def test_s15_duplicate_step_labels(graph: types.ModuleType, tmp_path: Path):
    bare_dup = (
        "### Task 1: A\n**Blocked by:** None\n"
        "- [ ] **Step 1: a**\n- [ ] **Step 2: b**\n- [ ] **Step 2: c**\n"
    )
    findings = check(graph, tmp_path, plan=bare_dup)
    assert any("duplicate step" in f for f in findings)
    lettered_dup = (
        "### Task 1: A\n**Blocked by:** None\n"
        "- [ ] **Step 1: a**\n- [ ] **Step 2a: b**\n- [ ] **Step 2a: c**\n"
    )
    findings = check(graph, tmp_path, plan=lettered_dup)
    assert any("duplicate step" in f for f in findings)


def test_s15_lettered_variants_count_as_base(graph: types.ModuleType, tmp_path: Path):
    plan = (
        "### Task 1: A\n**Blocked by:** None\n"
        "- [ ] **Step 1: a**\n- [ ] **Step 2: b**\n- [ ] **Step 2a: c**\n"
        "- [ ] **Step 2b: d**\n- [ ] **Step 3: e**\n"
    )
    assert check(graph, tmp_path, plan=plan) == []


def test_s15_real_lettered_packages_stay_clean(graph: types.ModuleType, tmp_path: Path):
    # mailbox-receiver-cli Task 8: Steps 1, 2a, 2b, 3, 4
    assert check(graph, tmp_path, plan=MAILBOX_TASK8) == []
    # settings-sync-engine Task 16: Steps 1, 1b, 2, 3, 3b, 4, 5, 6 (its
    # out-of-fixture Task 15 blocker is a dangling-ref finding, not a step one)
    findings = check(graph, tmp_path, plan=ENGINE_TASK16)
    assert not [f for f in findings if "step" in f.lower()]
