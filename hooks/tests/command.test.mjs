import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const entry = fileURLToPath(new URL("../command.mjs", import.meta.url));
const cases = JSON.parse(
  readFileSync(
    new URL("./fixtures/command-cases.json", import.meta.url),
    "utf8",
  ),
);
const payloads = {
  claude: (command) => ({
    hook_event_name: "PreToolUse",
    tool_name: "Bash",
    tool_input: { command },
  }),
  codex: (command) => ({
    hook_event_name: "PreToolUse",
    tool_name: "Bash",
    tool_input: { command },
  }),
  goose: (command) => ({
    event: "PreToolUse",
    tool_name: "shell",
    tool_input: { command },
  }),
  agy: (command) => ({
    toolCall: {
      name: "run_command",
      args: { CommandLine: command, Cwd: "/tmp" },
    },
  }),
};
function invoke(host, payload) {
  return spawnSync(process.execPath, [entry, host], {
    input: JSON.stringify(payload),
    encoding: "utf8",
  });
}
for (const [host, payload] of Object.entries(payloads)) {
  test(`${host}: denies a command using the native protocol`, () => {
    const result = invoke(host, payload("sudo true"));
    assert.equal(result.status, 0, result.stderr);
    const output = JSON.parse(result.stdout);
    if (host === "claude" || host === "codex") {
      assert.equal(output.hookSpecificOutput.permissionDecision, "deny");
      assert.equal(output.hookSpecificOutput.hookEventName, "PreToolUse");
    } else assert.equal(output.decision, host === "goose" ? "block" : "deny");
  });
  test(`${host}: passing hook leaves native permissions in control`, () => {
    const result = invoke(host, payload("git status"));
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, "");
  });
  test(`${host}: malformed protected command fails closed at adapter boundary`, () => {
    const result = invoke(host, payload(42));
    assert.equal(result.status, 2);
    assert.match(result.stderr, /command/i);
  });
}
test("malformed JSON emits a blocking exit code with clean stdout", () => {
  const result = spawnSync(process.execPath, [entry, "claude"], {
    input: "{",
    encoding: "utf8",
  });
  assert.equal(result.status, 2);
  assert.equal(result.stdout, "");
});
test("unknown host is rejected", () => {
  const result = invoke("typo", {});
  assert.equal(result.status, 2);
  assert.match(result.stderr, /harness/);
});
test("unrelated tools defer to native permissions", () => {
  const result = invoke("codex", {
    hook_event_name: "PreToolUse",
    tool_name: "read",
    tool_input: { path: "sudo" },
  });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, "");
});
test("the shared core preserves the existing command corpus", async () => {
  const { decide } = await import("../core/command-policy.mjs");
  for (const group of cases.groups)
    for (const command of group.commands) {
      const result = decide(command);
      assert.equal(
        result.deny,
        group.expect === "deny",
        `${group.name}: ${command}`,
      );
      if (result.deny) assert.ok(result.reason.includes(group.needle));
    }
});

test("a missing policy module blocks instead of returning an ordinary crash", async (t) => {
  const { mkdtempSync, copyFileSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const dir = mkdtempSync(join(tmpdir(), "hook-missing-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const copy = join(dir, "command.mjs");
  copyFileSync(entry, copy);
  const result = spawnSync(process.execPath, [copy, "claude"], {
    input: JSON.stringify(payloads.claude("git status")),
    encoding: "utf8",
  });
  assert.equal(result.status, 2);
  assert.equal(result.stdout, "");
});

test("Claude compatibility entry resolves a deployed custom symlink", async (t) => {
  const { mkdtempSync, symlinkSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const home = mkdtempSync(join(tmpdir(), "hook home "));
  t.after(() => rmSync(home, { recursive: true, force: true }));
  symlinkSync(
    fileURLToPath(new URL("../../custom", import.meta.url)),
    join(home, "custom"),
  );
  const result = spawnSync(
    "bash",
    [join(home, "custom/hooks/check-bash-guard.sh")],
    {
      input: JSON.stringify(payloads.claude("sudo true")),
      encoding: "utf8",
    },
  );
  assert.equal(result.status, 0, result.stderr);
  assert.equal(
    JSON.parse(result.stdout).hookSpecificOutput.permissionDecision,
    "deny",
  );
});
