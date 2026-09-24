---
name: agent-config
description: 'Use whenever the user edits or asks about AI coding agent configuration: Claude Code, Codex, opencode, pi, goose, Gemini CLI/Antigravity, or no-mistakes. Covers skills, slash commands, agents, permissions, hooks, model/provider settings, rules files, and cross-harness sync. Also covers "why did my change not take effect?" and "where does this setting live?". Shared configuration comes from the agent-config source checkout; edit its source and sync the managed artifact. Codex merges shared defaults while preserving local state. Excludes non-agent configuration: git, npm, shells, editors, and project build settings.'
---

# Agent Harness Configuration & Authoring

The checkout selected by `agent-config doctor` (normally `~/gitrepos/agent-config`) is the Single Source of Truth (SOT) for shared configuration across 7 harnesses: Claude Code, Codex, Opencode, Pi, Goose, Antigravity (`agy`), and no-mistakes. Sync regenerates managed artifacts; each harness retains its local state.

## Red Flags - STOP

- Editing any file under `~/.config/opencode/`, `~/.gemini/`, `~/.pi/agent/`, `~/.config/goose/`, or `~/.no-mistakes/` directly
- Editing template-managed keys in `~/.codex/config.toml` or generated `~/.codex/AGENTS.md` directly
- Naming skills with uppercase letters, underscores, or mismatched directory names
- Calling interactive modal question tools (`ask_question`, `AskUserQuestion`) instead of regular chat text
- Writing frontmatter with leading whitespace or comments before the initial `---`
- Forgetting the 3-step sync runbook after editing files in the source checkout

## Routing Table

| If asked or tempted to edit... | STOP. Edit this repo-relative file in the source checkout... | Then run sync command... |
|---|---|---|
| `~/.claude/settings.json` | `harnesses/claude/settings.json`; machine allow additions in `$XDG_CONFIG_HOME/agent-config/overlays/claude.json` | `agent-config sync claude config` |
| `~/.claude/CLAUDE.md` | `rules/global.md` | `agent-config sync claude context` |
| `~/.codex/config.toml` (shared model, permissions, features, MCP) | `harnesses/codex/config.toml` | `agent-config sync codex config`; launch plain `codex` |
| `~/.codex/AGENTS.md` | `rules/global.md` | `agent-config sync codex agents-md` |
| `~/.agents/skills/<skill>` | `skills/<skill>/SKILL.md` | native Codex discovery; inspect with `/skills` |
| `~/.gemini/antigravity-cli/settings.json` | `harnesses/gemini/settings.json` | `agent-config sync agy` |
| `~/.gemini/config/AGENTS.md` | `rules/global.md` | `agent-config sync agy` |
| `~/.gemini/config/skills/<skill>` | `skills/<skill>/SKILL.md` | `agent-config sync agy` |
| `~/.config/opencode/opencode.json` | `harnesses/opencode/opencode.json` | `agent-config sync opencode` |
| `~/.config/opencode/tui.json` | `harnesses/opencode/tui.json` | `agent-config sync opencode` |
| `~/.config/opencode/AGENTS.md` | `rules/global.md` (or `harnesses/opencode/rules.md` for opencode-only rules) | `agent-config sync opencode` |
| `~/.config/opencode/agents/<agent>.md` | `agents/<agent>.md` | `agent-config sync opencode` |
| `~/.config/opencode/commands/<cmd>.md` | `commands/<cmd>.md` | `agent-config sync opencode` |
| `~/.pi/agent/settings.json` | `harnesses/pi/settings.json` | `agent-config sync pi` |
| `~/.pi/agent/CLAUDE.md` | `rules/global.md` | `agent-config sync pi` |
| `~/.pi/agent/keybindings.json` | `harnesses/pi/keybindings.json` | `agent-config sync pi` |
| `~/.config/goose/config.yaml` | `harnesses/goose/config.yaml` | `agent-config sync goose` |
| `~/.config/goose/.goosehints` | `rules/global.md` | `agent-config sync goose` |
| `~/.config/goose/custom_providers/*.json` | `harnesses/goose/custom_providers/*.json` | `agent-config sync goose` |
| `~/.no-mistakes/config.yaml` (shared keys: timeouts, auto-fix limits, ...) | `harnesses/no-mistakes/config.yaml` | `agent-config sync no-mistakes` |
| `~/.no-mistakes/config.yaml` (machine/local keys: `agent`, `agent_path_override`, `worktree_roots`, ...) | `$XDG_CONFIG_HOME/agent-config/overlays/no-mistakes.yaml` (local overlay) | `agent-config sync no-mistakes` |

Codex sync recursively merges the template's declared keys into `~/.codex/config.toml`, preserving local keys and formatting. Project trust, hook approvals, and UI state stay local. Keys removed from the template retain their installed values until explicitly changed or removed locally. `CODEX_HOME` is honored; an explicit `--codex-dir` wins. See `harnesses/codex/README.md`, "Config ownership".

## Rationalizations

| Excuse | Reality |
|---|---|
| "Faster to edit `~/.config/opencode/opencode.json` directly" | Derived file. Overwritten on next sync/pull. Edit `harnesses/opencode/opencode.json` in repo. |
| "Edited `harnesses/gemini/settings.json`, harness sees it now" | No. Harness reads derived file. Must run `agent-config sync agy`. |
| "Hand-edited `~/.no-mistakes/config.yaml`, it works now" | Derived from template plus machine overlay. Next sync destroys the edit. Shared keys → `harnesses/no-mistakes/config.yaml`, machine/local keys (incl. day-to-day `agent` choice) → the local agent-config overlay, then `agent-config sync no-mistakes`. |
| "Only edited docs in `skills/`, don't need tests" | `settings-sync` validates regex & frontmatter. Invalid skill breaks Opencode. Run pytest. |
| "Can use `ask_question` modal tool here" | Non-portable. Breaks harnesses without modal UI. Always use chat text. |

## Authoring Portable Skills & Commands

- **Naming**: Directory name must match frontmatter `name` and regex `^[a-z0-9]+(-[a-z0-9]+)*$` (enforced by Opencode and `settings-sync`).
- **Frontmatter**: Exact `---\n` byte 0 start, `\n---\n` close. Required fields: `name` and `description` (under 1024 chars).
- **Portability**: Output questions/prompts in standard markdown chat text. Never invoke interactive modal tools.
- **Commands**: Slash commands go in `commands/<name>.md` with frontmatter `description`.
- **Methodology**: Use `writing-skills` for skill TDD.

## Rules, Submodules & Hooks

- Global rules live in `rules/global.md`. `@skills/<name>` references are auto-transformed into `the \`<name>\` skill` for Codex, Pi, Opencode, Goose, AGY.
- Harness-specific rules go in `harnesses/<tool>/rules.md` (e.g. `harnesses/opencode/rules.md`).
- Submodules (`custom/plugins/`) are symlinked into `skills/`. Run `git submodule update --init --recursive` after clone/pull.
- Hooks (`hooks/`) are Claude Code only and not bridged.

## 3-Step Verification Runbook

1. **Sync**: `agent-config sync <tool>`; normal generated updates need no force. A local-edit conflict requires selected-step `--force`, which creates a backup. Shared declared config keys merge on every sync.
2. **Test**: `uv run --directory ~/gitrepos/agent-config/settings-sync pytest`
3. **Drift Check**: `agent-config check <tool>`. `agent-config doctor <tool>` adds explicit native skill diagnostics.

## Commands and diagnostics

Install from the checkout root: `uv tool install --editable ./settings-sync`. Use `agent-config sync [harness] [step]`, `agent-config check [harness]`, and `agent-config doctor [harness]`. Source selection uses `--source`, `AGENT_CONFIG_REPO`, then the local agent-config pointer. External package installation is explicit: `agent-config bootstrap [harness]`; no-mistakes installation always requires selecting it.

Generated artifacts have ownership records under `$XDG_STATE_HOME/agent-config`. Identical outputs are adopted, source updates apply normally, and unknown files survive cleanup. Local keys omitted from a shared JSON/YAML/TOML template remain installed. Doctor performs harness-specific skill diagnostics; config sync is independent of unrelated skill lint.
