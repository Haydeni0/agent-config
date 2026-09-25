// Tests for the bash-guard opencode plugin.
//
// Command cases are loaded from command-cases.json (shared with the
// Claude check-bash-guard.sh hook test at ~/.claude/custom/hooks/).
// Harness-specific tests (plugin no-op when tool !== "bash", missing args)
// stay here - they have no Claude hook analogue.
//
// Two layers are tested here:
//   1. decide(command)        - pure function, the policy logic
//   2. BashGuard plugin       - tool.execute.before wrapper that throws on deny
//
// Run:  node --test bash-guard.test.mjs

import { test } from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { decide, BashGuard } from "./bash-guard.js"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const CASES_PATH = path.resolve(__dirname, "../../../hooks/tests/fixtures/command-cases.json")
const CASES = JSON.parse(readFileSync(CASES_PATH, "utf8"))

// -- shared corpus (parametrized from command-cases.json) -------------
// Add a command to the JSON and it flows into both this test and the Claude
// hook test. The loop below is the thin harness; the corpus is the source of
// truth for what's blocked/allowed.

for (const g of CASES.groups) {
  for (const command of g.commands) {
    test(`${g.label}: ${JSON.stringify(command)}`, () => {
      const r = decide(command)
      if (g.expect === "deny") {
        assert.equal(r.deny, true, `expected deny for ${JSON.stringify(command)}, got allow`)
        assert.ok(r.reason.includes(g.needle),
          `expected reason to include ${JSON.stringify(g.needle)}, got ${JSON.stringify(r.reason)}`)
      } else {
        assert.equal(r.deny, false, `expected allow for ${JSON.stringify(command)}, got deny: ${r.reason}`)
      }
    })
  }
}

// -- plugin wrapper (tool.execute.before) ----------------------------------
// Harness-specific: the Claude hook only runs on Bash (matcher gated), so
// these no-op cases have no Claude analogue.

test("plugin throws on bash delete", async () => {
  const plugin = await BashGuard()
  const handler = plugin["tool.execute.before"]
  await assert.rejects(
    () => handler({ tool: "bash" }, { args: { command: "aws s3 rm s3://bucket/foo" } }),
    /S3/,
  )
})

test("plugin no-op when tool is not bash (read)", async () => {
  const plugin = await BashGuard()
  const handler = plugin["tool.execute.before"]
  // must not throw
  await handler({ tool: "read" }, { args: { filePath: "/etc/passwd" } })
})

test("plugin no-op on empty bash command", async () => {
  const plugin = await BashGuard()
  const handler = plugin["tool.execute.before"]
  await handler({ tool: "bash" }, { args: { command: "" } })
})

test("plugin no-op on missing args", async () => {
  const plugin = await BashGuard()
  const handler = plugin["tool.execute.before"]
  await handler({ tool: "bash" }, {})
})

test("plugin no-op on missing output", async () => {
  const plugin = await BashGuard()
  const handler = plugin["tool.execute.before"]
  await handler({ tool: "bash" }, undefined)
})
