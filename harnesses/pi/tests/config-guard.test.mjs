import assert from "node:assert/strict";
import test from "node:test";
import { createJiti } from "jiti";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const live = path.join(os.tmpdir(), "agent-config-pi-live");
const source = fileURLToPath(new URL("../../../", import.meta.url)).replace(/\/$/, "");
const jiti = createJiti(import.meta.url, {
  tryNative: false,
  virtualModules: { "@earendil-works/pi-coding-agent": { getAgentDir: () => live } },
});
const { default: register } = await jiti.import("../extensions/config-guard.ts");
let callback;
register({ on: (event, handler) => { assert.equal(event, "tool_call"); callback = handler; } });
const invoke = (toolName, input) => callback({ toolName, input }, { hasUI: false });

for (const target of [live, path.join(os.homedir(), ".pi/agent")]) {
  test(`direct edits route to source: ${target}`, async () => {
    const result = await invoke("write", { path: path.join(target, "settings.json") });
    assert.equal(result.block, true);
    assert.ok(result.reason.includes(source));
    assert.ok(result.reason.includes("agent-config sync pi"));
  });
}
for (const [tool, input] of [
  ["edit", { path: path.join(source, "harnesses/pi/settings.json") }],
  ["bash", { command: "agent-config sync pi" }],
  ["bash", { command: `cat ${live}/settings.json` }],
]) {
  test(`source/sync/read allowed: ${tool} ${JSON.stringify(input)}`, async () => {
    assert.equal(await invoke(tool, input), undefined);
  });
}
