// config-guard.test.mjs - tests for the opencode config-guard plugin.
// Run with: node --test config-guard.test.mjs
//
// The guard blocks write/edit/apply_patch and bash writes to the derived
// opencode config dir. bashWritesTo splits the command into segments on
// newlines and shell separators first, then checks each segment's first word
// against write ops and each redirect's resolved target - so a write verb or
// redirect in ANY segment is caught, while a write verb and the dir as
// unrelated words (quoted prose, different segment) are not.

import assert from "node:assert/strict"
import test from "node:test"
import { mkdtempSync, rmSync } from "node:fs"
import os from "node:os"
import path from "node:path"

// CONFIG_DIR is resolved from OPENCODE_CONFIG_DIR at module load - env must
// be set before the dynamic import below.
const dir = mkdtempSync(path.join(os.tmpdir(), "config-guard-test-"))
process.env.OPENCODE_CONFIG_DIR = dir
const { ConfigGuard } = await import("./config-guard.js")

const hook = (await ConfigGuard())["tool.execute.before"]

process.on("exit", () => rmSync(dir, { recursive: true, force: true }))

async function runBash(command) {
  await hook({ tool: "bash" }, { args: { command } })
}

async function runWrite(filePath) {
  await hook({ tool: "write" }, { args: { filePath } })
}

async function assertBlocked(fn, label) {
  await assert.rejects(fn, /BLOCKED:.*derived target/, label)
}

// ---------- bash: write ops pointed at the dir ----------

for (const [label, command] of [
  ["redirect overwrite", `echo x > ${dir}/config.json`],
  ["redirect append", `echo x >> ${dir}/config.json`],
  ["tee", `tee ${dir}/x`],
  ["rm", `rm ${dir}/x`],
  ["sed -i", `sed -i s/a/b/ ${dir}/x`],
  ["cp into dir", `cp /tmp/src ${dir}/x`],
  ["&& chain: write op after &&", `echo ok && tee ${dir}/x`],
  ["; chain: write op after ;", `echo ok; tee ${dir}/x`],
  ["pipe into tee", `echo hi | tee ${dir}/x`],
  ["newline-separated write op (the gap this test locks)", `echo ok\ntee ${dir}/x`],
  ["crlf-separated write op", `echo ok\r\ntee ${dir}/x`],
  ["newline-separated redirect", `echo ok\necho x > ${dir}/config.json`],
  ["env-prefixed write op", `FOO=1 tee ${dir}/x`],
  ["sudo-stripped write op", `sudo tee ${dir}/x`],
  ["redirect split by backslash-newline continuation", `echo x > \\\n${dir}/config.json`],
  ["write op split by backslash-newline continuation", `echo ok\\\n && tee ${dir}/x`],
]) {
  test(`bash blocked: ${label}`, async () => {
    await assertBlocked(() => runBash(command), label)
  })
}

// ---------- bash: reads and unrelated writes stay allowed ----------

for (const [label, command] of [
  ["cat", `cat ${dir}/x`],
  ["ls", `ls ${dir}`],
  ["grep", `grep pattern ${dir}/x`],
  ["read with stderr silenced", `cat ${dir}/x 2>/dev/null`],
  ["sed without -i reads", `sed s/a/b/ ${dir}/x`],
  ["newline-separated read", `echo ok\ncat ${dir}/x`],
  ["redirect to elsewhere", `echo x > /dev/null`],
  ["dir named inside quoted prose", `git commit -m "tee ${dir}"`],
  ["write op for a different target", `tee /tmp/unrelated`],
]) {
  test(`bash allowed: ${label}`, async () => {
    await runBash(command) // no throw
  })
}

// ---------- write/edit tools ----------

test("write tool to dir blocked", async () => {
  await assertBlocked(() => runWrite(path.join(dir, "config.json")), "write tool")
})

test("edit tool to dir blocked", async () => {
  await assertBlocked(() => hook({ tool: "edit" }, { args: { filePath: path.join(dir, "x.json") } }), "edit tool")
})

test("write tool outside dir allowed", async () => {
  await runWrite("/tmp/unrelated.json") // no throw
})

test("write tool with no path allowed", async () => {
  await runWrite("") // no throw
})

test("blocked writes name source checkout and runnable sync", async () => {
  const source = path.resolve(import.meta.dirname, "../../..");
  await assert.rejects(() => runWrite(`${dir}/opencode.json`), error => {
    assert.ok(error.message.includes(source));
    assert.ok(error.message.includes("agent-config sync opencode"));
    return true;
  });
  await runWrite(path.join(source, "harnesses/opencode/opencode.json"));
  await runBash("agent-config sync opencode");
});
