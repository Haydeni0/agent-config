# codex

Shared defaults for [OpenAI Codex CLI](https://github.com/openai/codex). Sync merges the keys declared in `codex/config.toml` into `~/.codex/config.toml`, preserving other keys and local TOML formatting.

## Setup and launch

```bash
uv run --directory ~/.claude/settings-sync sync codex
codex
```

The defaults select Astra, high reasoning, fast service, and full access with command approvals disabled. Edit `codex/config.toml` here, then sync again. Plain `codex` loads the resulting user config automatically.

Explicit profiles, trusted project config, and command-line flags can override these defaults. See [Codex configuration precedence](https://learn.chatgpt.com/docs/config-file/config-basic#configuration-precedence).

For a custom Codex home, pass `--codex-dir /path/to/codex-home` before the `codex` sync subcommand. Use the same directory as the client’s `CODEX_HOME`.

## What syncs

| Source in `~/.claude` | Target in `~/.codex` | Mechanism |
|---|---|---|
| `codex/config.toml` | `config.toml` | merge declared keys; retain local keys and formatting |
| `CLAUDE.md` | `AGENTS.md` | `@skills/<n>` rewritten to `the \`<n>\` skill` (codex reads global instructions from `$CODEX_HOME/AGENTS.md`) |
| `skills/` | (native) | codex reads `~/.agents/skills` (user-scope root); sync.sh symlinks that at `~/.claude/skills` |

Use Codex's `/skills` to inspect discovery, including nested and symlinked skills. Opencode-specific skill lint applies to the other sync groups; `sync codex` manages its defaults and global instructions.

`sync codex --check` checks managed defaults and global instructions for drift. Global instructions retain the normal conflict protection: use `sync codex agents-md --force` after updating `CLAUDE.md`.

## Config ownership

Tables merge recursively. Declared scalar and array values replace the corresponding installed values. Other keys, including project trust, hook approval hashes, and UI state, stay local. Keep credentials and machine-specific paths out of the template.

Removing a key from the template releases it from management; its installed value remains until explicitly changed or removed locally. Malformed source or target TOML fails sync and preserves the target. `--check` and `--dry-run` report changes without writing.

## Not synced

- **Commands** (`commands/`) - codex slash commands use the skills format; Claude command markdown isn't read natively. Skills already cover most workflows; convert later if missed.
- **Hooks** - different hook model (`~/.codex/hooks.json`). Recreate per-hook if needed.
- **MCP servers** - Claude gets Linear/Slack/Notion via plugins; codex plugins use different marketplaces. Shared `[mcp_servers]` entries can go in `codex/config.toml`; credentials stay local.
- **evo** - no codex host in `evo install` (claude-code + opencode only).
- **Statusline, sessions, memory** - Claude Code specific; codex has its own.

## Notes

- Codex's first-run migration wizard offers a one-shot import from `~/.claude` (CLAUDE.md, MCP, commands, sessions). Skip it - it copies once; sync regenerates continuously.
- `wire_api = "chat"` is removed upstream; only `"responses"` is supported. Custom providers (e.g. GLM) must expose a Responses API endpoint.
- `~/.codex/skills` is a deprecated codex skill root, still read but unused here - `~/.agents/skills` is the canonical cross-harness root.
