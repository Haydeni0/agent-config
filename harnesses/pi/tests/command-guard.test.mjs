import test from "node:test";
import assert from "node:assert/strict";
import { createJiti } from "jiti";
const jiti = createJiti(import.meta.url, { tryNative: false });
test("Pi command guard blocks destructive shell calls and defers reads", async () => {
  const { default: register } = await jiti.import(
    "../extensions/command-guard.ts",
  );
  let hook;
  register({
    on: (event, fn) => {
      assert.equal(event, "tool_call");
      hook = fn;
    },
  });
  assert.equal(
    (await hook({ toolName: "bash", input: { command: "sudo true" } })).block,
    true,
  );
  assert.equal(
    await hook({ toolName: "bash", input: { command: "git status" } }),
    undefined,
  );
  assert.equal(
    await hook({ toolName: "read", input: { path: "sudo" } }),
    undefined,
  );
});

test("Pi rejects malformed bash input", async () => {
  const { default: register } = await jiti.import(
    "../extensions/command-guard.ts",
  );
  let hook;
  register({
    on: (_, fn) => {
      hook = fn;
    },
  });
  assert.equal((await hook({ toolName: "bash" })).block, true);
  assert.equal(
    (await hook({ toolName: "bash", input: { command: 42 } })).block,
    true,
  );
});
