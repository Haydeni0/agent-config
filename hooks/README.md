# Shared hooks

Command decisions live in `core/command-policy.mjs`. Add a policy case to
`tests/fixtures/command-cases.json`, then change the core. Native adapters translate
payloads and decisions. A passing policy produces no permission grant: native
permissions remain responsible for approval.

Config-write heuristics live in `core/config-policy.mjs`; Opencode and Pi keep
their existing protected-directory sets. These command-string heuristics cover
the existing policy, not arbitrary program behavior or a filesystem sandbox.

## Coverage

| Harness | Command registration | Verification |
|---|---|---|
| Claude Code | Existing Bash hook, thin Bash/Node entry point | CLI 2.1.282: allow, deny, broken entry point, timeout |
| Codex | `hooks.json`, `PreToolUse` Bash mapping | CLI 0.157.0: allow, deny, broken entry point, timeout, untrusted hook |
| Opencode | `tool.execute.before` plugin | CLI 1.18.29: allow and deny |
| Pi | `tool_call` extension | CLI 0.80.6: allow and deny |
| Goose | `~/.agents/plugins/agent-config-goose/` | CLI 1.44.0: allow, deny, broken entry point, timeout |
| Antigravity | Named `agent-config` entry in native `hooks.json` | Adapter and sync tests only; CLI unavailable |
| no-mistakes | Selected child harness | Source inspection only; CLI unavailable |

Native smoke tests force a harmless `printf sudo > marker` through the actual
CLI and inspect the returned tool result and marker. A scripted loopback model
eliminates model refusal and credentials from the experiment. Tests cover
headless CLI execution on Linux, not every interactive mode or tool surface.

Claude/Codex/Goose block a broken command entry point. **All three installed
versions continue after hook timeout. Codex also skips untrusted hooks.** The
Goose template requests `on_failure: block`, as documented upstream, but the
installed 1.44.0 timeout probe still executes the tool. Plugin/extension load
failures and arbitrary executable content remain outside the verified
enforcement claim. Codex interactive
`write_stdin` calls do not repeat the command pre-check. See the native contracts:
[Claude](https://code.claude.com/docs/en/hooks),
[Codex](https://learn.chatgpt.com/docs/hooks),
[Goose](https://goose-docs.ai/docs/guides/context-engineering/hooks/),
[Antigravity](https://antigravity.google/docs/hooks).

no-mistakes launches native child processes, inherits environment with overlays,
and permits extra CLI arguments. Its default Claude/Codex/Pi launches retain
user-level configuration, but actual coverage depends on the selected child,
arguments, home and trust. This is source evidence, not an end-to-end pipeline
certification: [Claude launcher](https://github.com/kunchenguid/no-mistakes/blob/3aafd46c8a0caac95cc6992d01985e0b17f1c22a/internal/agent/claude.go),
[Codex launcher](https://github.com/kunchenguid/no-mistakes/blob/3aafd46c8a0caac95cc6992d01985e0b17f1c22a/internal/agent/codex.go),
[Pi launcher](https://github.com/kunchenguid/no-mistakes/blob/3aafd46c8a0caac95cc6992d01985e0b17f1c22a/internal/agent/pi.go),
[environment](https://github.com/kunchenguid/no-mistakes/blob/3aafd46c8a0caac95cc6992d01985e0b17f1c22a/internal/runenv/overlay.go).

## Install and update

Use Node.js 22+; the Claude compatibility entry also requires Bash and jq.
Command-hook sync records the available Node executable and absolute checkout
path, quoted for spaces. Rerun sync after moving the checkout or Node executable.
Opencode/Pi use their own JavaScript runtimes.

```sh
agent-config sync claude
agent-config sync codex
agent-config sync opencode
agent-config sync pi
agent-config sync goose
agent-config sync agy
agent-config check
agent-config doctor
```

`hooks` is also a selectable sync/check step for Codex, Goose and AGY. Claude
hooks share its `config` step; Opencode uses `plugins`; Pi discovers extensions
through its existing settings. Goose's user plugin location is independent of
`--goose-dir`, as required by its native discovery. Antigravity uses `--agy-dir`,
not the separate CLI settings directory. Review/approve changed Codex hook
registrations in Codex. Sync preserves native trust and approval records.

Hook groups have separate ownership snapshots under
`$XDG_STATE_HOME/agent-config/hooks/`. Initial exact matches are adopted; foreign
groups survive updates and removal. Local edits to an adopted group cause a
conflict; `--force` does not bypass it. Reconcile the group with the snapshot
before retrying. Antigravity's local `enabled` setting is preserved.

Changed existing native files are backed up under the adjacent `backups/`, with
metadata identifying their destinations. To roll back a hook update, stop the
harness, restore the native file and its preceding ownership snapshot together,
and select the previous source revision before syncing again. Config and state
writes are individually atomic and serialized between sync processes. A crash
between those writes can require manual reconciliation; keep the reported
backup until the next sync/check succeeds. Native applications can still edit
settings concurrently, so sync checks for changes before replacing a file.

## Tests

```sh
bash scripts/verify.sh
node hooks/tests/native-smoke.mjs claude
node hooks/tests/native-smoke.mjs codex
node hooks/tests/native-smoke.mjs opencode
node hooks/tests/native-smoke.mjs pi
node hooks/tests/native-smoke.mjs goose
```

Routine CI exercises the shared corpus, adapters, config guards and isolated sync
updates/removal. Native probes require the named installed CLI, create temporary
homes/workspaces, and use only harmless marker commands. Codex probes bypass
hook trust for enforcement cases and separately verify the untrusted case.
Timeout/untrusted observations deliberately report marker creation as the native
behavior, not protection. Re-run probes after relevant host upgrades.

## Remaining lifecycle work

Caveman activation/tracking, Worktrunk status and vendor Herdr handlers retain
their native registrations. Cross-harness lifecycle parity needs a separate
choice of session-scoped mode state and multi-session marker ownership; this
branch consolidates safety policy and deployment first. Existing Claude
`gh api` prompting also remains alongside the shared hard-deny policy.
