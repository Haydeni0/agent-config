#!/usr/bin/env node
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join } from "node:path";

/** The mailbox turn-end guard adapter: find this session's mesh memberships,
 * check their unread mail read-only, and block the Stop while any waits.
 *
 * Fails OPEN, silently: unlike the permission guards (fail closed), a broken
 * mesh or malformed payload must never wedge every turn end in the session -
 * a documented exception to REQ-HARNESS-03 (REQ-HOOKS-07). Every early exit
 * is a one-readdir no-op at most: Stop fires on every turn end machine-wide,
 * and most sessions are not in a mesh. */

const INBOX_TIMEOUT_MS = 10_000;

function allow() {
  process.exit(0);
}

function membershipsFor(projectDir, sessionId) {
  const found = [];
  const work = join(projectDir, ".agents", "work");
  if (!existsSync(work)) return found;
  for (const pkg of readdirSync(work, { withFileTypes: true })) {
    if (!pkg.isDirectory()) continue;
    const members = join(work, pkg.name, "mailbox", "members");
    if (!existsSync(members)) continue;
    for (const file of readdirSync(members, { withFileTypes: true })) {
      if (!file.isFile()) continue;
      // the member file's harness-session line names this session without a herdr call
      const text = readFileSync(join(members, file.name), "utf8");
      if (!text.split("\n").some((line) => line === `harness-session=${sessionId}`)) continue;
      found.push({ mailbox: join(work, pkg.name, "mailbox"), member: file.name });
    }
  }
  return found;
}

function unreadLinesFor(mailbox) {
  // inbox is the side-effect-free listing (REQ-MAILBOX-05): a dying turn never
  // mutates mesh state through this guard
  const proc = spawnSync(join(mailbox, "bin", "mailbox"), ["inbox"], {
    timeout: INBOX_TIMEOUT_MS,
    encoding: "utf8",
  });
  if (proc.error || proc.status !== 0) return null; // stale seat, missing env: skip this mesh
  const output = (proc.stdout ?? "").trim();
  if (output === "" || output === "no unread mail") return [];
  return output.split("\n").map((line) => line.trim()).filter(Boolean);
}

try {
  const harness = process.argv[2];
  if (harness !== "claude") allow(); // only Claude Code exposes a turn-end event today
  const payload = JSON.parse(readFileSync(0, "utf8"));
  if (payload.hook_event_name !== "Stop") allow();
  if (payload.agent_id) allow(); // SubagentStop fires separately; the main session owns the inbox
  const projectDir = process.env.CLAUDE_PROJECT_DIR || payload.cwd;
  if (!projectDir) allow();
  const memberships = [];
  for (const { mailbox, member } of membershipsFor(projectDir, payload.session_id)) {
    const unreadLines = unreadLinesFor(mailbox);
    if (unreadLines) memberships.push({ mailbox, member, unreadLines });
  }
  const { decide } = await import("./core/mailbox-guard-policy.mjs");
  const result = decide({ stopHookActive: Boolean(payload.stop_hook_active), memberships });
  if (result.block) {
    process.stderr.write(result.reason + "\n");
    process.exit(2);
  }
} catch {
  allow(); // fail open: a malformed payload or unreadable mesh never wedges a turn end
}
