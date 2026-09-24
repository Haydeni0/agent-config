---
name: agent-config
description: 'Use whenever the user edits or asks about AI coding agent configuration: Claude Code, Codex, opencode, pi, goose, Gemini CLI/Antigravity, or no-mistakes. Covers skills, slash commands, agents, permissions, hooks, model/provider settings, rules files, and cross-harness sync. Also covers "why did my change not take effect?" and "where does this setting live?". Shared configuration comes from ~/.claude; edit its source and sync the managed artifact. Codex merges shared defaults while preserving local state. Excludes non-agent configuration: git, npm, shells, editors, and project build settings.'
---

# Agent Harness Configuration & Authoring

`~/.claude` is the Single Source of Truth (SOT) for shared configuration across 7 harnesses: Claude Code, Codex, Opencode, Pi, Goose, Antigravity (`agy`), and no-mistakes. Sync regenerates managed artifacts; each harness retains its local state.

## Red Flags - STOP

- Editing any file under `~/.config/opencode/`, `~/.gemini/`, `~/.pi/agent/`, `~/.config/goose/`, or `~/.no-mistakes/` directly
- Editing template-managed keys in `~/.codex/config.toml` or generated `~/.codex/AGENTS.md` directly
- Naming skills with uppercase letters, underscores, or mismatched directory names
- Calling interactive modal question tools (`ask_question`, `AskUserQuestion`) instead of regular chat text
- Writing frontmatter with leading whitespace or comments before the initial `---`
- Forgetting the 3-step sync runbook after editing files in `~/.claude/`

## Routing Table

| If asked or tempted to edit... | STOP. Edit this repo-relative file in `~/.claude`... | Then run sync command... |
|---|---|---|
| `~/.codex/config.toml` (shared model, permissions, features, MCP) | `codex/config.toml` | `sync codex config`; launch plain `codex` |
| `~/.codex/AGENTS.md` | `CLAUDE.md` | `sync codex agents-md --force` |
| `~/.agents/skills/<skill>` | `skills/<skill>/SKILL.md` | native Codex discovery; inspect with `/skills` |
| `~/.gemini/antigravity-cli/settings.json` | `gemini/settings.json` | `sync agy --force` |
| `~/.gemini/config/AGENTS.md` | `CLAUDE.md` | `sync agy --force` |
| `~/.gemini/config/skills/<skill>` | `skills/<skill>/SKILL.md` | `sync agy --force` |
| `~/.config/opencode/opencode.json` | `opencode/opencode.json` | `sync opencode --force` |
| `~/.config/opencode/tui.json` | `opencode/tui.json` | `sync opencode --force` |
| `~/.config/opencode/AGENTS.md` | `CLAUDE.md` (or `opencode/rules.md` for opencode-only rules) | `sync opencode --force` |
| `~/.config/opencode/agents/<agent>.md` | `agents/<agent>.md` | `sync opencode --force` |
| `~/.config/opencode/commands/<cmd>.md` | `commands/<cmd>.md` | `sync opencode --force` |
| `~/.pi/agent/settings.json` | `pi/settings.json` | `sync pi --force` |
| `~/.pi/agent/CLAUDE.md` | `CLAUDE.md` | `sync pi --force` |
| `~/.pi/agent/keybindings.json` | `pi/keybindings.json` | `sync pi --force` |
| `~/.config/goose/config.yaml` | `goose/config.yaml` | `sync goose --force` |
| `~/.config/goose/.goosehints` | `CLAUDE.md` | `sync goose --force` |
| `~/.config/goose/custom_providers/*.json` | `goose/custom_providers/*.json` | `sync goose --force` |
| `~/.no-mistakes/config.yaml` (shared keys: timeouts, auto-fix limits, ...) | `no-mistakes/config.yaml` | `sync no-mistakes` |
| `~/.no-mistakes/config.yaml` (machine/local keys: `agent`, `agent_path_override`, `worktree_roots`, ...) | `no-mistakes/config.local.yaml` (untracked overlay) | `sync no-mistakes` |

Codex sync recursively merges the template's declared keys into `~/.codex/config.toml`, preserving local keys and formatting. Project trust, hook approvals, and UI state stay local. Keys removed from the template retain their installed values until explicitly changed or removed locally. For a custom `CODEX_HOME`, pass the matching `--codex-dir` before the sync subcommand. See `codex/README.md`, "Config ownership".

## Rationalizations

| Excuse | Reality |
|---|---|
| "Faster to edit `~/.config/opencode/opencode.json` directly" | Derived file. Overwritten on next sync/pull. Edit `opencode/opencode.json` in repo. |
| "Edited `gemini/settings.json`, harness sees it now" | No. Harness reads derived file. Must run `sync agy --force`. |
| "Hand-edited `~/.no-mistakes/config.yaml`, it works now" | Derived + always-overwrite (pi model). Next sync destroys the edit. Shared keys → `no-mistakes/config.yaml`, machine/local keys (incl. day-to-day `agent` choice) → `config.local.yaml`, then `sync no-mistakes`. |
| "Only edited docs in `skills/`, don't need tests" | `settings-sync` validates regex & frontmatter. Invalid skill breaks Opencode. Run pytest. |
| "Can use `ask_question` modal tool here" | Non-portable. Breaks harnesses without modal UI. Always use chat text. |

## Authoring Portable Skills & Commands

- **Naming**: Directory name must match frontmatter `name` and regex `^[a-z0-9]+(-[a-z0-9]+)*$` (enforced by Opencode and `settings-sync`).
- **Frontmatter**: Exact `---\n` byte 0 start, `\n---\n` close. Required fields: `name` and `description` (under 1024 chars).
- **Portability**: Output questions/prompts in standard markdown chat text. Never invoke interactive modal tools.
- **Commands**: Slash commands go in `commands/<name>.md` with frontmatter `description`.
- **Methodology**: Use `writing-skills` for skill TDD.

## Rules, Submodules & Hooks

- Global rules live in `CLAUDE.md`. `@skills/<name>` references are auto-transformed into `the \`<name>\` skill` for Codex, Pi, Opencode, Goose, AGY.
- Harness-specific rules go in `<tool>/rules.md` (e.g. `opencode/rules.md`).
- Submodules (`custom/plugins/`) are symlinked into `skills/`. Run `git submodule update --init --recursive` after clone/pull.
- Hooks (`hooks/`) are Claude Code only and not bridged.

## 3-Step Verification Runbook

1. **Sync**: `uv run --directory ~/.claude/settings-sync sync <tool>`; use the routing table's `--force` for intentional replacements. Codex defaults merge on every sync.
2. **Test**: `uv run --directory ~/.claude/settings-sync pytest`
3. **Drift Check**: `uv run --directory ~/.claude/settings-sync sync <tool> --check`. Bare `sync --check` also checks other harnesses and their skill compatibility.
