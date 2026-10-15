import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const entry = fileURLToPath(new URL("../mailbox-guard.mjs", import.meta.url));
const cases = JSON.parse(
  readFileSync(
    new URL("./fixtures/mailbox-guard-cases.json", import.meta.url),
    "utf8",
  ),
);

function invoke(input, env) {
  return spawnSync(process.execPath, [entry, "claude"], {
    input,
    encoding: "utf8",
    env: { ...process.env, ...env },
  });
}

// the pure core: the corpus is the source of truth for block/allow
{
  const { decide } = await import("../core/mailbox-guard-policy.mjs");
  for (const { name, facts, expected } of cases) {
    test(`corpus: ${name}`, () => {
      const result = decide(facts);
      assert.equal(result.block, expected.block, result.reason);
      if (expected.reasonContains) {
        for (const fragment of expected.reasonContains)
          assert.ok(result.reason.includes(fragment), `reason missing ${fragment}: ${result.reason}`);
      }
      if (expected.reasonAbsent) {
        for (const fragment of expected.reasonAbsent)
          assert.ok(!result.reason.includes(fragment), `reason must not contain ${fragment}: ${result.reason}`);
      }
    });
  }
}

const SESSION_ID = "sess-guard-test";

function stageProject() {
  const project = join(tmpdir(), `guard-proj-${process.pid}-${Date.now()}`);
  mkdirSync(project, { recursive: true });
  return project;
}

function stageMembership(project, pkg, member, stubOutput, stubStatus = 0) {
  const mailbox = join(project, ".agents", "work", pkg, "mailbox");
  mkdirSync(join(mailbox, "members", member, ".."), { recursive: true });
  writeFileSync(
    join(mailbox, "members", member),
    `role=x\npane=w1:p1\nsession=s1\nharness=claude\nharness-session=${SESSION_ID}\n`,
  );
  mkdirSync(join(mailbox, "bin"), { recursive: true });
  const argvLog = join(mailbox, "argv.log");
  writeFileSync(
    join(mailbox, "bin", "mailbox"),
    `#!/bin/sh\nprintf '%s\\n' "$@" >> '${argvLog}'\n${stubStatus === 0 ? `printf '%s\\n' ${JSON.stringify(stubOutput)}` : `exit ${stubStatus}`}\n`,
  );
  chmodSync(join(mailbox, "bin", "mailbox"), 0o755);
  return { mailbox, argvLog };
}

function stopPayload(extra = {}) {
  return JSON.stringify({
    hook_event_name: "Stop",
    session_id: SESSION_ID,
    stop_hook_active: false,
    ...extra,
  });
}

test("silent no-op for a non-Stop event", () => {
  const result = invoke(JSON.stringify({ hook_event_name: "SessionStart", session_id: SESSION_ID }), {});
  assert.equal(result.status, 0);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr, "");
});

test("silent no-op for a subagent stop", () => {
  const result = invoke(stopPayload({ agent_id: "sub-1" }), {});
  assert.equal(result.status, 0);
  assert.equal(result.stderr, "");
});

test("silent no-op with no project dir to scan", () => {
  const result = invoke(stopPayload({ cwd: undefined }), { CLAUDE_PROJECT_DIR: "" });
  assert.equal(result.status, 0);
  assert.equal(result.stderr, "");
});

test("silent no-op when the project has no .agents/work", () => {
  const project = stageProject();
  const result = invoke(stopPayload({ cwd: project }), { CLAUDE_PROJECT_DIR: project });
  assert.equal(result.status, 0);
  assert.equal(result.stderr, "");
});

test("silent no-op when no member file matches the session", () => {
  const project = stageProject();
  stageMembership(project, "pkg", "planner", "no unread mail");
  const result = invoke(
    stopPayload({ session_id: "some-other-session" }),
    { CLAUDE_PROJECT_DIR: project },
  );
  assert.equal(result.status, 0);
  assert.equal(result.stderr, "");
});

test("silent no-op when the member's inbox is empty", () => {
  const project = stageProject();
  stageMembership(project, "pkg", "planner", "no unread mail");
  const result = invoke(stopPayload({ cwd: project }), { CLAUDE_PROJECT_DIR: project });
  assert.equal(result.status, 0);
  assert.equal(result.stderr, "");
});

test("blocks with take-then-ack fix commands when mail is unread", () => {
  const project = stageProject();
  const { mailbox } = stageMembership(project, "pkg", "planner", "001-x  from worker  msg  12 B");
  const result = invoke(stopPayload({ cwd: project }), { CLAUDE_PROJECT_DIR: project });
  assert.equal(result.status, 2);
  assert.ok(result.stderr.includes(`${mailbox}/bin/mailbox take`), result.stderr);
  assert.ok(result.stderr.includes(`${mailbox}/bin/mailbox ack`), result.stderr);
  assert.ok(result.stderr.includes("001-x"), result.stderr);
});

test("the unread check is read-only: the mesh helper sees exactly inbox", () => {
  const project = stageProject();
  const { argvLog } = stageMembership(project, "pkg", "planner", "001-x  from worker  msg  12 B");
  invoke(stopPayload({ cwd: project }), { CLAUDE_PROJECT_DIR: project });
  assert.ok(existsSync(argvLog));
  assert.deepEqual(readFileSync(argvLog, "utf8").trim().split("\n"), ["inbox"]);
});

test("stop_hook_active allows the stop: one forced follow-up per chain", () => {
  const project = stageProject();
  stageMembership(project, "pkg", "planner", "001-x  from worker  msg  12 B");
  const result = invoke(
    stopPayload({ cwd: project, stop_hook_active: true }),
    { CLAUDE_PROJECT_DIR: project },
  );
  assert.equal(result.status, 0);
  assert.equal(result.stderr, "");
});

test("a failing mesh helper skips that mesh silently", () => {
  const project = stageProject();
  stageMembership(project, "broken", "planner", "", 3); // stale seat / missing env shape
  const result = invoke(stopPayload({ cwd: project }), { CLAUDE_PROJECT_DIR: project });
  assert.equal(result.status, 0);
  assert.equal(result.stderr, "");
});

test("malformed payload fails open, silently", () => {
  const result = invoke("not json", {});
  assert.equal(result.status, 0);
  assert.equal(result.stderr, "");
});

test("an unknown harness is a silent no-op", () => {
  const result = spawnSync(process.execPath, [entry, "opencode"], {
    input: stopPayload(),
    encoding: "utf8",
  });
  assert.equal(result.status, 0);
  assert.equal(result.stderr, "");
});
