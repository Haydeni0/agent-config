#!/usr/bin/env node
import { readFileSync } from "node:fs";

/** Translate native pre-tool payloads without granting native permission. */
function commandFor(harness, input) {
  if (!input || typeof input !== "object" || Array.isArray(input))
    throw new Error("Expected a hook object");
  switch (harness) {
    case "claude":
    case "codex":
      if (input.hook_event_name !== "PreToolUse")
        throw new Error("Expected PreToolUse event");
      if (input.tool_name !== "Bash") return null;
      return input.tool_input?.command;
    case "goose":
      if (input.event !== "PreToolUse")
        throw new Error("Expected PreToolUse event");
      if (input.tool_name !== "shell") return null;
      return input.tool_input?.command;
    case "agy":
      if (!input.toolCall || typeof input.toolCall.name !== "string")
        throw new Error("Expected toolCall");
      if (input.toolCall.name !== "run_command") return null;
      return input.toolCall.args?.CommandLine;
    default:
      throw new Error("Unknown hook harness");
  }
}

try {
  const harness = process.argv[2];
  const command = commandFor(harness, JSON.parse(readFileSync(0, "utf8")));
  if (command !== null) {
    if (typeof command !== "string")
      throw new Error("Expected a string command");
    const { decide } = await import("./core/command-policy.mjs");
    const result = decide(command);
    if (result.deny) {
      const output =
        harness === "claude" || harness === "codex"
          ? {
              hookSpecificOutput: {
                hookEventName: "PreToolUse",
                permissionDecision: "deny",
                permissionDecisionReason: result.reason,
              },
            }
          : {
              decision: harness === "goose" ? "block" : "deny",
              reason: result.reason,
            };
      process.stdout.write(JSON.stringify(output) + "\n");
    }
  }
} catch (error) {
  const reason =
    error instanceof SyntaxError
      ? "Invalid hook JSON or policy syntax"
      : error.code
        ? "Cannot load command policy"
        : error.message;
  process.stderr.write(`Command guard failed: ${reason}\n`);
  process.exitCode = 2;
}
