"""Subprocess tests for the agent-mailbox helper against a fake herdr on PATH.

The fake keeps an agent-name -> pane map in a JSON state file, applies
renames, can be told to fail `wait` / `prompt` for a named agent with a herdr
error code, and logs every invocation so tests can assert what was rung.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parent / "mailbox.py"
PLANNER_PANE = "w1:p1"
WORKER_PANE = "w1:p2"
CRITIC_PANE = "w1:p3"

FAKE_HERDR = r'''#!/usr/bin/env python3
import json, os, sys

state_path = os.environ["FAKE_HERDR_STATE"]
with open(state_path) as f:
    state = json.load(f)
with open(os.environ["FAKE_HERDR_LOG"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")


def fail(code):
    print(json.dumps({"error": {"code": code, "message": code}, "id": "fake"}))
    sys.exit(1)


_group, verb, target, *rest = sys.argv[1:]
agents = state["agents"]
if verb == "rename":
    state["agents"] = {n: p for n, p in agents.items() if p != target}
    state["agents"][rest[0]] = target
    with open(state_path, "w") as f:
        json.dump(state, f)
    print("{}")
    sys.exit(0)
override = state.get(verb, {}).get(target)
if override:
    fail(override)
if target not in agents:
    fail("agent_not_found")
if verb == "get":
    print(json.dumps({"result": {"agent": {"pane_id": agents[target]}}}))
    sys.exit(0)
print("{}")
'''


@dataclass(slots=True)
class FakeHerdr:
    env: dict[str, str]
    state_path: Path
    log_path: Path

    def set(self, key: str, value: dict[str, str]) -> None:
        state = json.loads(self.state_path.read_text())
        state[key] = value
        self.state_path.write_text(json.dumps(state))

    def calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.log_path.read_text().splitlines()]

    def clear_log(self) -> None:
        self.log_path.write_text("")


@dataclass(slots=True)
class Mesh:
    root: Path
    herdr: FakeHerdr

    def run(self, *args: str, pane: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        env = {**self.herdr.env, "HERDR_PANE_ID": pane}
        return subprocess.run(
            [sys.executable, str(self.root / "bin" / "mailbox"), *args],
            input=stdin, capture_output=True, text=True, env=env,
        )

    def inbox(self, name: str) -> Path:
        return self.root / "inboxes" / name


@pytest.fixture
def fake_env(tmp_path: Path) -> FakeHerdr:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    herdr = fakebin / "herdr"
    herdr.write_text(FAKE_HERDR)
    herdr.chmod(0o755)
    state_path = tmp_path / "herdr-state.json"
    state_path.write_text(json.dumps({"agents": {}}))
    log_path = tmp_path / "herdr-log.jsonl"
    log_path.write_text("")
    env = {
        **os.environ,
        "PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}",
        "FAKE_HERDR_STATE": str(state_path),
        "FAKE_HERDR_LOG": str(log_path),
    }
    return FakeHerdr(env=env, state_path=state_path, log_path=log_path)


def run_init(root: Path, herdr: FakeHerdr) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HELPER), "init", str(root)],
        capture_output=True, text=True, env=herdr.env,
    )


@pytest.fixture
def empty_mesh(tmp_path: Path, fake_env: FakeHerdr) -> Mesh:
    root = (tmp_path / "mailbox").resolve()
    result = run_init(root, fake_env)
    assert result.returncode == 0, result.stderr
    return Mesh(root=root, herdr=fake_env)


@pytest.fixture
def mesh(empty_mesh: Mesh) -> Iterator[Mesh]:
    for name, pane in (("planner", PLANNER_PANE), ("worker", WORKER_PANE), ("critic", CRITIC_PANE)):
        result = empty_mesh.run("join", name, "--role", name, pane=pane)
        assert result.returncode == 0, result.stderr
    empty_mesh.herdr.clear_log()
    yield empty_mesh


def test_init_creates_layout_and_fills_absolute_paths_into_contract(tmp_path: Path, fake_env: FakeHerdr) -> None:
    root = (tmp_path / "mailbox").resolve()

    result = run_init(root, fake_env)

    assert result.returncode == 0, result.stderr
    assert (root / "members").is_dir()
    assert (root / "inboxes").is_dir()
    assert os.access(root / "bin" / "mailbox", os.X_OK)
    readme = (root / "README.md").read_text()
    assert "{{MAILBOX}}" not in readme
    assert f"{root}/bin/mailbox send" in readme


def test_init_refuses_a_non_empty_directory(tmp_path: Path, fake_env: FakeHerdr) -> None:
    root = tmp_path / "mailbox"
    root.mkdir()
    (root / "something").write_text("x")

    result = run_init(root, fake_env)

    assert result.returncode != 0
    assert "not empty" in result.stderr
    assert not (root / "README.md").exists()


def test_commands_outside_an_initialised_mailbox_are_refused(fake_env: FakeHerdr) -> None:
    result = subprocess.run(
        [sys.executable, str(HELPER), "join", "planner", "--role", "x"],
        capture_output=True, text=True, env={**fake_env.env, "HERDR_PANE_ID": PLANNER_PANE},
    )

    assert result.returncode != 0
    assert "not an initialised mailbox" in result.stderr


def test_join_renames_herdr_agent_and_creates_member_and_inbox(empty_mesh: Mesh) -> None:
    result = empty_mesh.run("join", "planner", "--role", "plans the work", pane=PLANNER_PANE)

    assert result.returncode == 0, result.stderr
    assert (empty_mesh.root / "members" / "planner").read_text() == "role=plans the work\n"
    assert (empty_mesh.inbox("planner") / "handled").is_dir()
    assert ["agent", "rename", PLANNER_PANE, "planner"] in empty_mesh.herdr.calls()


@pytest.mark.parametrize("name", ["Planner", "plan.ner", "plan_ner", "-planner", "planner-"])
def test_join_rejects_names_unsafe_in_filenames(empty_mesh: Mesh, name: str) -> None:
    result = empty_mesh.run("join", name, "--role", "x", pane=PLANNER_PANE)

    assert result.returncode != 0
    assert list((empty_mesh.root / "members").iterdir()) == []


def test_join_refuses_a_name_held_by_another_pane(empty_mesh: Mesh) -> None:
    empty_mesh.herdr.set("agents", {"planner": "w9:p9"})

    result = empty_mesh.run("join", "planner", "--role", "x", pane=PLANNER_PANE)

    assert result.returncode != 0
    assert "w9:p9" in result.stderr
    assert not any(call[1] == "rename" for call in empty_mesh.herdr.calls())


def test_join_takes_over_a_dead_members_name(empty_mesh: Mesh) -> None:
    (empty_mesh.root / "members" / "planner").write_text("role=old\n")

    result = empty_mesh.run("join", "planner", "--role", "new", pane=PLANNER_PANE)

    assert result.returncode == 0, result.stderr
    assert (empty_mesh.root / "members" / "planner").read_text() == "role=new\n"


def test_join_without_a_herdr_pane_is_refused(empty_mesh: Mesh) -> None:
    result = empty_mesh.run("join", "planner", "--role", "x", pane="")

    assert result.returncode != 0
    assert "HERDR_PANE_ID" in result.stderr
