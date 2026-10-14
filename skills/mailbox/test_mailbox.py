"""Subprocess tests for the mailbox helper against a fake herdr on PATH.

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
SESSION = "s1"

FAKE_HERDR = r'''#!/usr/bin/env python3
import json, os, sys

state_path = os.environ["FAKE_HERDR_STATE"]
with open(state_path) as f:
    state = json.load(f)
with open(os.environ["FAKE_HERDR_LOG"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")


def fail(code):
    print(json.dumps({"error": {"code": code, "message": code}, "id": "fake"}), file=sys.stderr)
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
    harness = state.get("harness", {}).get(target, "claude")
    print(json.dumps({"result": {"agent": {"pane_id": agents[target], "agent": harness}}}))
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

    def run(self, *args: str, pane: str, session: str | None = SESSION, stdin: str = "") -> subprocess.CompletedProcess[str]:
        env = {**self.herdr.env, "HERDR_PANE_ID": pane}
        # the developer's own herdr session leaks in through os.environ
        env.pop("HERDR_SESSION", None)
        if session is not None:
            env["HERDR_SESSION"] = session
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
    assert (empty_mesh.root / "members" / "planner").read_text() == f"role=plans the work\npane={PLANNER_PANE}\nsession={SESSION}\n"
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
    assert (empty_mesh.root / "members" / "planner").read_text() == f"role=new\npane={PLANNER_PANE}\nsession={SESSION}\n"


def test_join_without_a_herdr_pane_is_refused(empty_mesh: Mesh) -> None:
    result = empty_mesh.run("join", "planner", "--role", "x", pane="")

    assert result.returncode != 0
    assert "HERDR_PANE_ID" in result.stderr


def test_join_clears_its_seat_from_the_member_file_it_rejoined_away_from(mesh: Mesh) -> None:
    result = mesh.run("join", "lead", "--role", "leads", pane=PLANNER_PANE)

    assert result.returncode == 0, result.stderr
    assert (mesh.root / "members" / "planner").read_text() == "role=planner\n"
    sent = mesh.run("send", "x", "worker", "--no-ring", pane=PLANNER_PANE, stdin="b")
    assert sent.returncode == 0, sent.stderr
    assert (mesh.inbox("worker") / "lead.001-x.msg").exists()


def test_join_keeps_a_same_pane_claim_from_another_herdr_session(mesh: Mesh) -> None:
    result = mesh.run("join", "remote", "--role", "x", pane=PLANNER_PANE, session="s2")

    assert result.returncode == 0, result.stderr
    assert (mesh.root / "members" / "planner").read_text() == f"role=planner\npane={PLANNER_PANE}\nsession={SESSION}\n"


def test_two_member_files_claiming_one_seat_fail_loudly(mesh: Mesh) -> None:
    (mesh.root / "members" / "ghost").write_text(f"role=x\npane={PLANNER_PANE}\nsession={SESSION}\n")

    result = mesh.run("send", "x", "worker", "--no-ring", pane=PLANNER_PANE, stdin="b")

    assert result.returncode != 0
    assert "ghost" in result.stderr
    assert "planner" in result.stderr
    assert not list(mesh.inbox("worker").glob("*.msg"))


def test_send_resolves_the_sender_without_calling_herdr(mesh: Mesh) -> None:
    result = mesh.run("send", "x", "worker", "--no-ring", pane=PLANNER_PANE, stdin="b")

    assert result.returncode == 0, result.stderr
    assert mesh.herdr.calls() == []


def test_commands_without_a_herdr_session_are_refused(mesh: Mesh) -> None:
    result = mesh.run("send", "x", "worker", "--no-ring", pane=PLANNER_PANE, session=None, stdin="b")

    assert result.returncode != 0
    assert "HERDR_SESSION" in result.stderr


def wake_line(mesh: Mesh, name: str) -> str:
    return f": mail waiting in {mesh.root}/inboxes/{name}/ - follow {mesh.root}/README.md"


def worker_has_a_request_and_a_reply(mesh: Mesh) -> None:
    """Leave worker's inbox holding planner.001-review-api.msg and planner.001-ask.reply - both <planner, 001>."""
    for args, pane, body in (
        (("send", "review-api", "worker"), PLANNER_PANE, "review it\n"),
        (("send", "ask", "planner"), WORKER_PANE, "which api?\n"),
        (("reply", "001-ask", "worker"), PLANNER_PANE, "here is the answer\n"),
    ):
        result = mesh.run(*args, "--no-ring", pane=pane, stdin=body)
        assert result.returncode == 0, result.stderr
    mesh.herdr.clear_log()


def test_inbox_lists_unread_mail_with_citable_ids_and_takes_nothing(mesh: Mesh) -> None:
    worker_has_a_request_and_a_reply(mesh)

    result = mesh.run("inbox", pane=WORKER_PANE)

    assert result.returncode == 0, result.stderr
    assert "001-review-api  from planner  msg" in result.stdout
    assert "001-ask  from planner  reply" in result.stdout
    unread = {p.name for p in mesh.inbox("worker").iterdir() if p.is_file()}
    assert unread == {"planner.001-review-api.msg", "planner.001-ask.reply"}
    assert mesh.herdr.calls() == []


def test_inbox_with_nothing_unread_says_so_and_exits_zero(mesh: Mesh) -> None:
    result = mesh.run("inbox", pane=WORKER_PANE)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "no unread mail"


def test_send_writes_request_named_by_sender_seq_and_slug(mesh: Mesh) -> None:
    result = mesh.run("send", "review-api", "worker", "--no-ring", pane=PLANNER_PANE, stdin="review it\n")

    assert result.returncode == 0, result.stderr
    assert (mesh.inbox("worker") / "planner.001-review-api.msg").read_text() == "review it\n"


def test_send_seq_continues_past_handled_requests(mesh: Mesh) -> None:
    mesh.run("send", "first", "worker", "--no-ring", pane=PLANNER_PANE, stdin="a")
    (mesh.inbox("worker") / "planner.001-first.msg").rename(mesh.inbox("worker") / "handled" / "planner.001-first.msg")

    result = mesh.run("send", "second", "worker", "--no-ring", pane=PLANNER_PANE, stdin="b")

    assert result.returncode == 0, result.stderr
    assert (mesh.inbox("worker") / "planner.002-second.msg").exists()


def test_send_broadcast_writes_the_same_id_to_every_recipient(mesh: Mesh) -> None:
    result = mesh.run("send", "plan-ready", "worker", "critic", "--no-ring", pane=PLANNER_PANE, stdin="look\n")

    assert result.returncode == 0, result.stderr
    assert (mesh.inbox("worker") / "planner.001-plan-ready.msg").read_text() == "look\n"
    assert (mesh.inbox("critic") / "planner.001-plan-ready.msg").read_text() == "look\n"


def test_send_to_a_non_member_is_refused_before_any_write(mesh: Mesh) -> None:
    result = mesh.run("send", "x", "worker", "ghost", "--no-ring", pane=PLANNER_PANE, stdin="b")

    assert result.returncode != 0
    assert "ghost" in result.stderr
    assert not list(mesh.inbox("worker").glob("*.msg"))


def test_send_with_an_empty_body_is_refused(mesh: Mesh) -> None:
    result = mesh.run("send", "x", "worker", "--no-ring", pane=PLANNER_PANE, stdin="  \n")

    assert result.returncode != 0
    assert not list(mesh.inbox("worker").glob("*.msg"))


def test_send_from_a_pane_that_has_not_joined_is_refused(mesh: Mesh) -> None:
    result = mesh.run("send", "x", "worker", "--no-ring", pane="w5:p5", stdin="b")

    assert result.returncode != 0
    assert "join" in result.stderr


def test_reply_reuses_the_request_id_with_the_replier_as_sender(mesh: Mesh) -> None:
    result = mesh.run("reply", "001-review-api", "planner", "--no-ring", pane=WORKER_PANE, stdin="looks good\n")

    assert result.returncode == 0, result.stderr
    assert (mesh.inbox("planner") / "worker.001-review-api.reply").read_text() == "looks good\n"


def test_reply_never_overwrites_an_existing_reply(mesh: Mesh) -> None:
    (mesh.inbox("planner") / "handled" / "worker.001-review-api.reply").write_text("first\n")

    result = mesh.run("reply", "001-review-api", "planner", "--no-ring", pane=WORKER_PANE, stdin="second\n")

    assert result.returncode != 0
    assert not (mesh.inbox("planner") / "worker.001-review-api.reply").exists()


def test_reply_rejects_an_id_without_a_sequence_number(mesh: Mesh) -> None:
    result = mesh.run("reply", "review-api", "planner", "--no-ring", pane=WORKER_PANE, stdin="x")

    assert result.returncode != 0


def test_writes_leave_no_temporary_files(mesh: Mesh) -> None:
    mesh.run("send", "x", "worker", "--no-ring", pane=PLANNER_PANE, stdin="b")

    assert [p.name for p in mesh.inbox("worker").iterdir() if p.name.startswith(".")] == []


def test_ring_waits_for_idle_then_prompts_a_pointer_to_the_contract(mesh: Mesh) -> None:
    result = mesh.run("send", "x", "worker", pane=PLANNER_PANE, stdin="b")

    assert result.returncode == 0, result.stderr
    calls = mesh.herdr.calls()
    assert ["agent", "wait", "worker", "--until", "idle", "--until", "done", "--timeout", "30000"] in calls
    assert ["agent", "prompt", "worker", wake_line(mesh, "worker")] in calls
    assert result.stdout.strip().endswith("rung")


@pytest.mark.parametrize(
    ("verb", "code", "reported"),
    [
        ("prompt", "agent_blocked", "permission prompt"),
        ("wait", "agent_not_found", "no live herdr agent"),
    ],
)
def test_unrung_outcomes_are_reported_and_the_message_kept(mesh: Mesh, verb: str, code: str, reported: str) -> None:
    mesh.herdr.set(verb, {"worker": code})

    result = mesh.run("send", "x", "worker", pane=PLANNER_PANE, stdin="b")

    assert result.returncode == 0, result.stderr
    assert reported in result.stdout
    assert (mesh.inbox("worker") / "planner.001-x.msg").exists()
    if verb == "wait":
        assert not any(call[1] == "prompt" for call in mesh.herdr.calls())


def test_ring_prompts_a_busy_claude_recipient_mid_turn(mesh: Mesh) -> None:
    mesh.herdr.set("wait", {"worker": "timeout"})

    result = mesh.run("send", "x", "worker", pane=PLANNER_PANE, stdin="b")

    assert result.returncode == 0, result.stderr
    assert ["agent", "prompt", "worker", wake_line(mesh, "worker")] in mesh.herdr.calls()
    assert "rung while busy" in result.stdout
    assert (mesh.inbox("worker") / "planner.001-x.msg").exists()


def test_ring_leaves_a_busy_non_claude_recipient_to_its_own_check(mesh: Mesh) -> None:
    mesh.herdr.set("wait", {"worker": "timeout"})
    mesh.herdr.set("harness", {"worker": "codex"})

    result = mesh.run("send", "x", "worker", pane=PLANNER_PANE, stdin="b")

    assert result.returncode == 0, result.stderr
    assert "not idle" in result.stdout
    assert not any(call[1] == "prompt" for call in mesh.herdr.calls())
    assert (mesh.inbox("worker") / "planner.001-x.msg").exists()


def test_an_unexpected_herdr_error_fails_loudly_after_the_write(mesh: Mesh) -> None:
    mesh.herdr.set("prompt", {"worker": "socket_gone"})

    result = mesh.run("send", "x", "worker", pane=PLANNER_PANE, stdin="b")

    assert result.returncode == 1
    assert "socket_gone" in result.stdout
    assert (mesh.inbox("worker") / "planner.001-x.msg").exists()


def test_no_ring_skips_herdr_wait_and_prompt(mesh: Mesh) -> None:
    mesh.run("send", "x", "worker", "--no-ring", pane=PLANNER_PANE, stdin="b")

    assert not any(call[1] in ("wait", "prompt") for call in mesh.herdr.calls())
