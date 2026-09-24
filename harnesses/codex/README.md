# codex

Shared defaults for [OpenAI Codex CLI](https://github.com/openai/codex). Sync merges the keys declared in `harnesses/codex/config.toml` into `~/.codex/config.toml`, preserving other keys and local TOML formatting.

## Setup and launch

```bash
agent-config sync codex
codex
```

The defaults select Astra, high reasoning, fast service, and full access with command approvals disabled. Edit `harnesses/codex/config.toml` here, then sync again. Plain `codex` loads the resulting user config automatically.

The native footer shows model and reasoning, directory, Git branch, approval mode, context usage, and estimated thread cost when available. It uses theme colors. Herdr displays the commit and push gates in its tab bar.

SQLite runtime state lives at `/var/tmp/hayden.dorahy/codex-sqlite`. The same absolute path resolves to node-local storage on each cluster machine, keeping WAL files off the shared home filesystem. Config sync creates the directory with mode `0700`; Codex also initializes a missing directory when first launched on a new node.

Explicit profiles, trusted project config, and command-line flags can override these defaults. See [Codex configuration precedence](https://learn.chatgpt.com/docs/config-file/config-basic#configuration-precedence).

For a custom Codex home, pass `--codex-dir /path/to/codex-home` before the `codex` sync subcommand. Use the same directory as the client’s `CODEX_HOME`.

## What syncs

| Source in the checkout | Target in `~/.codex` | Mechanism |
|---|---|---|
| `harnesses/codex/config.toml` | `config.toml` | merge declared keys; retain local keys and formatting |
| `harnesses/codex/config.toml` `sqlite_home` | configured local path | create directory with mode `0700` |
| `rules/global.md` | `AGENTS.md` | `@skills/<n>` rewritten to `the \`<n>\` skill` (codex reads global instructions from `$CODEX_HOME/AGENTS.md`) |
| `skills/` | (native) | codex reads `~/.agents/skills` (user-scope root); local sync links that at `~/.claude/skills` |

Use Codex's `/skills` to inspect discovery, including nested and symlinked skills. Opencode-specific skill lint runs through `agent-config doctor opencode`; `sync codex` manages its defaults and global instructions.

`sync codex --check` checks managed defaults and global instructions for drift. Changes to `rules/global.md` apply on normal sync. A local edit to generated instructions requires selected-step `--force`, which preserves a backup.

## Config ownership

Tables merge recursively. Declared scalar and array values replace the corresponding installed values. Other keys, including project trust, hook approval hashes, and undeclared UI state, stay local. Keep credentials and machine-specific paths out of the template.

Removing a key from the template releases it from management; its installed value remains until explicitly changed or removed locally. Malformed source or target TOML fails sync and preserves the target. `--check` and `--dry-run` report changes without writing.

## Not synced

- **Commands** (`commands/`) - codex slash commands use the skills format; Claude command markdown isn't read natively. Skills already cover most workflows; convert later if missed.
- **Hooks** - different hook model (`~/.codex/hooks.json`). Recreate per-hook if needed.
- **MCP servers** - Claude gets Linear/Slack/Notion via plugins; codex plugins use different marketplaces. Shared `[mcp_servers]` entries can go in `harnesses/codex/config.toml`; credentials stay local.
- **evo** - no codex host in `evo install` (claude-code + opencode only).
- **Sessions, memory** - Claude Code specific; codex has its own.

## Notes

- Codex's first-run migration wizard offers a one-shot import from `~/.claude` (CLAUDE.md, MCP, commands, sessions). Skip it - it copies once; sync regenerates continuously.
- `wire_api = "chat"` is removed upstream; only `"responses"` is supported. Custom providers (e.g. GLM) must expose a Responses API endpoint.
- `~/.codex/skills` is a deprecated codex skill root, still read but unused here - `~/.agents/skills` is the canonical cross-harness root.
