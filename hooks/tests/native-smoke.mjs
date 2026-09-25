// Native CLI probe with a loopback model. Every issued shell command is harmless.
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  readFileSync,
  existsSync,
  rmSync,
  symlinkSync,
  copyFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import assert from "node:assert/strict";

const host = process.argv[2];
assert.ok(
  ["codex", "claude", "pi", "opencode", "goose"].includes(host),
  "usage: node hooks/tests/native-smoke.mjs codex|claude|pi|opencode|goose",
);
const repo = fileURLToPath(new URL("../..", import.meta.url));
const quote = (s) => "'" + s.replaceAll("'", "'\\''") + "'";
const PROBE_TIMEOUT_MS = 45000;
for (const scenario of ["pi", "opencode"].includes(host)
  ? ["allow", "deny", "unicode-field"]
  : [
      "allow",
      "deny",
      "unicode-field",
      "broken",
      "timeout",
      ...(host === "codex" ? ["untrusted"] : []),
    ]) {
  const home = mkdtempSync(join(tmpdir(), `native-${host}-`));
  let server;
  let child;
  let timer;
  try {
    const cwd = join(home, "workspace");
    mkdirSync(cwd);
    const marker = join(cwd, "marker");
    // The local gh function records shell arguments without making API requests.
    const command = scenario === "unicode-field"
      ? `gh() { printf '%s\\n' "$@" > ${quote(marker)}; }\ngh api repos/OWNER/REPO/issues -f title=x\u00a0-X\u00a0GET`
      : `printf ${scenario === "allow" || scenario === "broken" ? "allowed" : "sudo"} > ${quote(marker)}`;
    const calls = [];
    server = createServer(async (req, res) => {
      let data = "";
      for await (const chunk of req) data += chunk;
      if (!req.url.includes("responses") && !req.url.includes("messages")) {
        res.writeHead(404);
        res.end();
        return;
      }
      const body = JSON.parse(data);
      calls.push(body);
      const usesMessages = host !== "codex";
      const done =
        !body.tools?.length ||
        (usesMessages
          ? body.messages.some(
              (m) =>
                Array.isArray(m.content) &&
                m.content.some((c) => c.type === "tool_result"),
            )
          : body.input.some((m) => m.type === "function_call_output"));
      res.writeHead(200, { "content-type": "text/event-stream" });
      const emit = (type, payload) =>
        res.write(
          `event: ${type}\ndata: ${JSON.stringify({ type, ...payload })}\n\n`,
        );
      if (usesMessages) {
        emit("message_start", {
          message: {
            id: "msg_probe",
            type: "message",
            role: "assistant",
            model: body.model,
            content: [],
            stop_reason: null,
            stop_sequence: null,
            usage: { input_tokens: 10, output_tokens: 1 },
          },
        });
        emit("content_block_start", {
          index: 0,
          content_block: done
            ? { type: "text", text: "" }
            : {
                type: "tool_use",
                id: "tool_probe",
                name:
                  host === "claude"
                    ? "Bash"
                    : host === "goose"
                      ? "shell"
                      : "bash",
                input: {},
              },
        });
        emit("content_block_delta", {
          index: 0,
          delta: done
            ? { type: "text_delta", text: "probe complete" }
            : {
                type: "input_json_delta",
                partial_json: JSON.stringify({
                  command,
                  description: "Harmless hook canary",
                }),
              },
        });
        emit("content_block_stop", { index: 0 });
        emit("message_delta", {
          delta: {
            stop_reason: done ? "end_turn" : "tool_use",
            stop_sequence: null,
          },
          usage: { output_tokens: 10 },
        });
        emit("message_stop", {});
      } else {
        const names = body.tools?.map((t) => t.name);
        const name = names.includes("exec_command") ? "exec_command" : "shell";
        const args =
          name === "exec_command"
            ? { cmd: command }
            : { command: ["bash", "-c", command] };
        const item = done
          ? {
              id: "msg_probe",
              type: "message",
              role: "assistant",
              status: "completed",
              content: [
                {
                  type: "output_text",
                  text: "probe complete",
                  annotations: [],
                },
              ],
            }
          : {
              id: "fc_probe",
              type: "function_call",
              name,
              call_id: "call_probe",
              arguments: JSON.stringify(args),
              status: "completed",
            };
        emit("response.created", {
          response: {
            id: "resp_probe",
            object: "response",
            status: "in_progress",
            output: [],
          },
        });
        emit("response.output_item.added", { output_index: 0, item });
        emit("response.output_item.done", { output_index: 0, item });
        emit("response.completed", {
          response: {
            id: "resp_probe",
            object: "response",
            status: "completed",
            output: [item],
            usage: { input_tokens: 10, output_tokens: 10, total_tokens: 20 },
          },
        });
      }
      res.end();
    });
    await new Promise((r) => server.listen(0, "127.0.0.1", r));
    const url = `http://127.0.0.1:${server.address().port}`;
    const entry =
      scenario === "broken"
        ? join(home, "missing.mjs")
        : join(repo, "hooks/command.mjs");
    const hook = `${quote(process.execPath)} ${quote(entry)} ${host}`;
    const nativeHome = join(home, `.${host}`);
    mkdirSync(nativeHome);
    if (host === "pi")
      writeFileSync(
        join(nativeHome, "models.json"),
        JSON.stringify({ providers: { anthropic: { baseUrl: url } } }),
      );
    if (["claude", "codex", "goose"].includes(host)) {
      const template = JSON.parse(
        readFileSync(
          join(
            repo,
            "harnesses",
            host,
            host === "claude" ? "settings.json" : "hooks.json",
          ),
          "utf8",
        ),
      );
      const config = { hooks: { PreToolUse: template.hooks.PreToolUse } };
      for (const group of config.hooks.PreToolUse)
        for (const action of group.hooks) {
          action.command = action.command.replace(
            "${AGENT_CONFIG_COMMAND}",
            hook,
          );
          if (scenario === "timeout") {
            action.command = "sleep 2";
            action.timeout = 1;
          }
        }
      let destination = join(
        nativeHome,
        host === "claude" ? "settings.json" : "hooks.json",
      );
      if (host === "claude") {
        if (scenario === "broken") {
          mkdirSync(join(nativeHome, "custom/hooks"), { recursive: true });
          copyFileSync(
            join(repo, "custom/hooks/check-bash-guard.sh"),
            join(nativeHome, "custom/hooks/check-bash-guard.sh"),
          );
        } else symlinkSync(join(repo, "custom"), join(nativeHome, "custom"));
      }
      if (host === "goose") {
        const plugin = join(home, ".agents/plugins/agent-config-goose");
        mkdirSync(join(plugin, "hooks"), { recursive: true });
        writeFileSync(
          join(plugin, "plugin.json"),
          JSON.stringify({ name: "agent-config-goose", version: "1.0.0" }),
        );
        destination = join(plugin, "hooks/hooks.json");
      }
      writeFileSync(destination, JSON.stringify(config));
    }
    if (host === "opencode")
      writeFileSync(
        join(nativeHome, "opencode.json"),
        JSON.stringify({
          provider: {
            anthropic: {
              options: { baseURL: url + "/v1", apiKey: "local-probe-key" },
            },
          },
          plugin: [
            pathToFileURL(
              join(repo, "harnesses/opencode/plugins/bash-guard.js"),
            ).href,
          ],
          permission: "allow",
        }),
      );
    const env = {
      PATH: process.env.PATH,
      HOME: home,
      XDG_CONFIG_HOME: join(home, ".config"),
      XDG_STATE_HOME: join(home, ".state"),
      XDG_CACHE_HOME: join(home, ".cache"),
      CODEX_HOME: nativeHome,
      CLAUDE_CONFIG_DIR: nativeHome,
      PI_CODING_AGENT_DIR: nativeHome,
      OPENCODE_CONFIG_DIR: nativeHome,
      ANTHROPIC_BASE_URL: url,
      ANTHROPIC_HOST: url,
      GOOSE_PROVIDER: "anthropic",
      GOOSE_MODEL: "claude-sonnet-4-6",
      GOOSE_MODE: "auto",
      ANTHROPIC_API_KEY: "local-probe-key",
      CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
    };
    const args =
      host === "goose"
        ? [
            "run",
            "--text",
            "Run the canary once.",
            "--no-session",
            "--no-profile",
            "--with-builtin",
            "developer",
            "--output-format",
            "stream-json",
            "--max-turns",
            "3",
          ]
        : host === "opencode"
          ? [
              "run",
              "--format",
              "json",
              "-m",
              "anthropic/claude-sonnet-4-6",
              "Run the canary once.",
            ]
          : host === "pi"
            ? [
                "-p",
                "Run the canary once.",
                "--mode",
                "json",
                "--provider",
                "anthropic",
                "--model",
                "claude-sonnet-4-6",
                "--no-session",
                "--offline",
                "--no-context-files",
                "--no-skills",
                "--no-prompt-templates",
                "--no-extensions",
                "-e",
                join(repo, "harnesses/pi/extensions/command-guard.ts"),
              ]
            : host === "codex"
              ? [
                  "exec",
                  "--skip-git-repo-check",
                  "--ephemeral",
                  "--json",
                  ...(scenario === "untrusted"
                    ? []
                    : ["--dangerously-bypass-hook-trust"]),
                  "--dangerously-bypass-approvals-and-sandbox",
                  "--enable",
                  "hooks",
                  "-m",
                  "gpt-5.4",
                  "-c",
                  'model_provider="probe"',
                  "-c",
                  `model_providers.probe={name="probe",base_url="${url}/v1",wire_api="responses",requires_openai_auth=false}`,
                  "Run the canary once.",
                ]
              : [
                  "-p",
                  "Run the canary once.",
                  "--verbose",
                  "--output-format",
                  "stream-json",
                  "--dangerously-skip-permissions",
                  "--no-session-persistence",
                  "--setting-sources",
                  "user",
                  "--tools",
                  "Bash",
                  "--model",
                  "claude-sonnet-4-6",
                ];
    let output = "";
    let errors = "";
    child = spawn(host, args, {
      cwd,
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    child.stdout.on("data", (c) => (output += c));
    child.stderr.on("data", (c) => (errors += c));
    timer = setTimeout(() => child.kill("SIGKILL"), PROBE_TIMEOUT_MS);
    const code = await new Promise((r, j) => {
      child.on("error", j);
      child.on("close", r);
    });
    clearTimeout(timer);
    server.closeAllConnections();
    await new Promise((r) => server.close(r));
    const evidence = {
      host,
      scenario,
      code,
      requests: calls.length,
      marker: existsSync(marker),
      markerContent: existsSync(marker) ? readFileSync(marker, "utf8") : null,
      output,
      errors,
      tools: calls[0]?.tools?.map((t) => t.name),
    };
    assert.equal(code, 0, JSON.stringify(evidence));
    const results = calls.flatMap((body) =>
      host === "codex"
        ? body.input.filter(
            (item) =>
              item.type === "function_call_output" &&
              item.call_id === "call_probe",
          )
        : body.messages.flatMap((message) =>
            Array.isArray(message.content)
              ? message.content.filter(
                  (item) =>
                    item.type === "tool_result" &&
                    item.tool_use_id === "tool_probe",
                )
              : [],
          ),
    );
    assert.ok(results.length > 0, JSON.stringify(evidence));
    assert.equal(
      existsSync(marker),
      scenario === "allow" ||
        scenario === "untrusted" ||
        scenario === "timeout",
      JSON.stringify(evidence),
    );
    if (scenario === "deny")
      assert.match(JSON.stringify(results), /sudo is not permitted/i);
    if (scenario === "unicode-field")
      assert.match(JSON.stringify(results), /gh api write methods are not permitted/i);
    console.log(
      JSON.stringify({
        host,
        scenario,
        result: ["timeout", "untrusted"].includes(scenario)
          ? "observed-native-limit"
          : "passed",
        requests: calls.length,
        marker: existsSync(marker),
      }),
    );
  } finally {
    clearTimeout(timer);
    if (child && child.exitCode === null) child.kill("SIGKILL");
    server?.closeAllConnections();
    if (server?.listening) server.close();
    rmSync(home, { recursive: true, force: true });
  }
}
