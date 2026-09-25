import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { decide } from "../../../hooks/core/command-policy.mjs";

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event) => {
    if (event.toolName !== "bash") return;
    const command = (event.input as { command?: unknown } | undefined)?.command;
    if (typeof command !== "string")
      return {
        block: true,
        reason: "Command guard: expected a string command",
      };
    const result = decide(command);
    if (result.deny) return { block: true, reason: result.reason };
  });
}
