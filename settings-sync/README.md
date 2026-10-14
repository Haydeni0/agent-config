# settings-sync

The `agent-config` CLI. Syncs the source checkout into Claude, opencode, pi, goose, agy, Codex, and no-mistakes. The source checkout owns the managed artifacts listed below; each harness keeps its own local state. Setup and the everyday loop live in the [root README](../README.md).

Shared skills and commands use each harness's native discovery where available; the tables below identify the artifacts that need conversion.

## What it syncs

### Claude

Shared `harnesses/claude/settings.json` merges into the native settings file. `rules/global.md` becomes global `CLAUDE.md` with source routing. Shared skills, commands and agents are installed as individual links; local skill containers remain in place. Compatibility links under `~/.claude` point into the source checkout:

| Alias | Source target | Reason |
|---|---|---|
| `custom`, `hooks` | same-named source directories | Hook commands and plugin imports |
| `statusline-command.sh` | `harnesses/claude/statusline-command.sh` | Native statusline command |
| `pi`, `opencode`, `codex`, `goose`, `gemini`, `no-mistakes` | corresponding `harnesses/` directories | Launchers and source references |
| `settings-sync`, `opencode-resume` | same-named source directories | Tool invocations |
| `sync.sh`, `scripts`, `README.md` | same-named source entries | Setup entry and navigation |

`--claude-home` selects a custom Claude runtime destination and renders hook commands accordingly.

### opencode

| Source in the checkout | Target in `~/.config/opencode` | Mechanism |
|---|---|---|
| `harnesses/opencode/opencode.json` (base config) | `opencode.json` | passthrough, adds `$schema` |
| `harnesses/opencode/tui.json` (TUI config) | `tui.json` | passthrough, adds `$schema` |
| `harnesses/opencode/rules.md` (opencode-only rules) | appended to `AGENTS.md` | safety rules appended after CLAUDE.md content |
| `rules/global.md` | `AGENTS.md` | `@skills/<n>` rewritten to `the \`<n>\` skill` |
| `agents/*.md` | `agents/*.md` | frontmatter transform (see below) |
| `commands/` | `commands/*.md` | generated commands and skill stubs |
| `plugins/cache/.../superpowers/<v>/.opencode/plugins/superpowers.js` | `plugins/superpowers.js` | relative symlink, highest semver resolved |
| `skills/` | (native) | opencode reads `~/.claude/skills` directly; doctor validates discovery |

Hooks (`hooks/`) are not bridged — opencode's plugin hook model differs. Recreate as an opencode plugin if needed.

### pi

| Source in the checkout | Target in `~/.pi/agent` | Mechanism |
|---|---|---|
| `harnesses/pi/settings.json` (pointer template) | `settings.json` | merge declared defaults; preserve local keys |
| `harnesses/pi/keybindings.json` (optional) | `keybindings.json` | generated file with ownership tracking |
| `rules/global.md` | `CLAUDE.md` | `@skills/<n>` rewritten (pi can't expand `@` refs) - skills/commands read directly (via pointers), doctor validates discovery |
| `skills/` | (native) | pi reads `~/.claude/skills` directly (via pointers); doctor validates discovery |
| `commands/` | (native) | pi reads `~/.claude/commands` directly (via pointers) |

Pi settings merge declared keys while retaining local state, including `lastChangelogVersion`. Keybindings are optional generated output. See [`harnesses/pi/README.md`](../harnesses/pi/README.md).

### goose

| Source in the checkout | Target in `~/.config/goose` | Mechanism |
|---|---|---|
| `rules/global.md` | `.goosehints` | `@skills/<n>` rewritten (same transform as opencode `AGENTS.md`) |
| `harnesses/goose/config.yaml` (base config) | `config.yaml` | merge declared defaults; preserve local keys |
| `harnesses/goose/custom_providers/*.json` | `custom_providers/*.json` | generated files; remove only unchanged managed orphans |
| `skills/` | (native) | goose reads `~/.claude/skills` directly via compat path; doctor validates discovery |
| `agents/` | (native) | goose reads `~/.claude/agents` directly via compat path; doctor validates discovery |

goose discovers skills and agents from `~/.claude` natively (backward-compat paths). Agent frontmatter: goose only reads `name`/`description`/`model` - Claude Code keys (`tools`/`disallowedTools`/`skills`) are ignored. Commands are not synced (goose slash commands use a different format - `config.yaml` entries mapping to recipe files). See [`harnesses/goose/README.md`](../harnesses/goose/README.md).

### agy

| Source in the checkout | Target | Mechanism |
|---|---|---|
| `harnesses/gemini/settings.json` | `~/.gemini/antigravity-cli/settings.json` | merge declared defaults; preserve local keys |
| `rules/global.md` | `~/.gemini/config/AGENTS.md` | `@skills/<n>` rewritten to `the \`<n>\` skill` |
| `skills/` | `~/.gemini/config/skills/` | managed relative links; preserve foreign entries |

`agy` (Antigravity) reads agent settings from `antigravity-cli/settings.json`, global rules from `AGENTS.md`, and discovers custom skills from `skills/`.

### no-mistakes

| Source in the checkout | Target in `~/.no-mistakes` | Mechanism |
|---|---|---|
| `harnesses/no-mistakes/config.yaml` (template, shared keys) | `config.yaml` | deep-merged with the overlay, then written |
| `$XDG_CONFIG_HOME/agent-config/overlays/no-mistakes.yaml` (overlay, machine/local keys incl. `agent`, untracked) | `config.yaml` | overlay wins at leaf level |

Fully derived: regenerated on every sync with no force gate, so hand edits to `~/.no-mistakes/config.yaml` die on the next sync. Which key goes in the template vs the overlay, template rules, agent switching, and update flow live in [`harnesses/no-mistakes/README.md`](../harnesses/no-mistakes/README.md). This target manages **only** `config.yaml` - everything else in `~/.no-mistakes` (binary, daemon state, db, worktrees, evidence) is untouched.

### codex

| Source in the checkout | Target in `~/.codex` | Mechanism |
|---|---|---|
| `harnesses/codex/config.toml` | `config.toml` | merge declared defaults; preserve local keys and formatting; plain `codex` loads them |
| `rules/global.md` | `AGENTS.md` | `@skills/<n>` rewritten (same transform as opencode's AGENTS.md) |
| `skills/` | (native) | codex reads `~/.agents/skills`, linked directly to the source checkout's `skills/`; inspect discovery with Codex's `/skills` |

Commands, hooks, and plugins are not bridged - codex uses different formats. See [`harnesses/codex/README.md`](../harnesses/codex/README.md).

Codex config tables merge recursively. The template owns the keys it declares; local keys, including project trust, hook approvals, and UI state, create no drift. Removing a template key leaves its installed value in place. Invalid TOML fails before writing. Use `--codex-dir` to target a custom `CODEX_HOME`.

## Usage

```bash
agent-config sync                      # every harness; refuses on conflict, exit 1 if any
agent-config sync codex                # one harness
agent-config sync codex agents-md      # one step (table below)
agent-config check [harness] [step]    # exit nonzero on drift, write nothing
agent-config doctor [harness]          # paths, sources, links, host availability
agent-config sync --dry-run            # preview, write nothing
agent-config sync goose --force        # back up and replace conflicting generated files
agent-config sync --verbose            # diffs for changed text artifacts
agent-config --pi-dir /tmp/glm-pi sync pi   # path overrides go before the subcommand
agent-config bootstrap [harness]       # install external packages; --dry-run to preview
```

| Harness | Steps |
|---|---|
| claude | `config`, `context`, `links` |
| opencode | `resources`, `config`, `tui`, `agents-md`, `agents`, `commands`, `plugins` |
| pi | `resources`, `config`, `context`, `keybindings` |
| goose | `hooks`, `resources`, `hints`, `config`, `providers` |
| agy | `hooks`, `settings`, `agents-md`, `skills` |
| codex | `hooks`, `skills`, `config`, `agents-md` |
| no-mistakes | `config` |

Path overrides: `--source` (alias `--claude-dir`), `--claude-home`, `--opencode-dir`, `--pi-dir`, `--goose-dir`, `--agy-dir`, `--agy-cli-dir`, `--nomistakes-dir`, `--codex-dir`. The legacy `sync` entry point (`sync [harness] [step]`, flags accepted anywhere, `--check` as a flag) stays available; it alone carries the opencode skill lint, `sync opencode skills`.

Install with `uv tool install --editable ./settings-sync` from the repo root. Python dependency changes require refreshing the editable tool environment; lockfile alternative: `uv run --locked --directory settings-sync agent-config`.

Source resolution: `--source`, then `AGENT_CONFIG_REPO`, then `source = "/absolute/repo"` in `$XDG_CONFIG_HOME/agent-config/config.toml`; an unconfigured source is an error. Native destinations are resolved per invocation; explicit destination flags beat `CODEX_HOME`, `OPENCODE_CONFIG_DIR`, and XDG defaults.

Bootstrap: `sync.sh` is a compatibility entry for it. It defaults to installed hosts; no-mistakes requires explicit selection because installation starts its daemon. Pi packages have exact versions/revisions in `harnesses/pi/settings.json`; web-access uses `npm ci`. Evo CLI/plugin and initial no-mistakes release pins live in `scripts/bootstrap.sh`. Native no-mistakes updates remain user-controlled.

## Ownership and recovery

Shared templates own the keys they declare. JSON/YAML/TOML mappings merge recursively; declared arrays/scalars replace; omitted keys stay local. Invalid source or installed config fails before writing. Codex retains TOML formatting. no-mistakes retains its explicit template-plus-overlay contract.

Hook event arrays reconcile adopted groups separately, preserving foreign registrations. See [shared hooks](../hooks/README.md#install-and-update) for snapshots, conflicts, native trust and rollback.

Generated instructions, commands, agents, providers, and links use `$XDG_STATE_HOME/agent-config/managed.json` (default `~/.local/state/agent-config/managed.json`). Identical existing outputs can be adopted. Unchanged managed outputs update normally; local edits cause conflicts. Selected-step `--force` backs up a conflicting file before replacement under the adjacent `backups/` directory, with a JSON record of its original destination. Restore that file to its recorded destination if needed.

Cleanup deletes only unchanged recorded outputs. Foreign files and real directories survive force; changed managed orphans remain conflicts. Checks and dry runs preserve config, links, ownership records, and timestamps. Installs use atomic replacement and detect edits since reading; advisory locks serialize generated-output writes, while native applications can still write their own settings.

The shared `~/.agents/skills` link points directly to the source checkout's `skills/` and is installed during Codex/full local sync. A foreign directory/link is reported and preserved, including with force. Claude's generated `~/.claude/skills/synced/` collection stays local to Claude. A managed legacy link updates only after its remaining visible entries resolve to their source counterparts. Inventory and reconcile those entries, then sync Claude links before Codex. Sync discovers source skills from the filesystem, including gitignored entries such as the local Chromium skill.

## Adding a harness

Add its adapter and one `Harness` declaration in `settings_sync/registry.py`, including ordered steps, required sources, destination, and host CLI. CLI selection, all-target runs, and diagnostics consume that declaration. Optional integration inputs belong outside required sources. Opencode skill lint runs explicitly through `sync opencode skills` or its doctor; config sync remains independent.

## Agent frontmatter transform (opencode only)

Claude Code `tools`/`disallowedTools`/`skills` map to opencode `permission`:

| Claude Code | opencode permission |
|---|---|
| `Read` | `read` |
| `Write`, `Edit`, `apply_patch` | `edit` |
| `Glob`, `Grep` | `glob`, `grep` |
| `Bash` | `bash` |
| `Agent`, `Task` | `task` |
| `List` | `list` |
| `TodoWrite` | `todowrite` |
| `Skill` | `skill` |
| `WebFetch` | `webfetch` |

- **Deny-by-default**: tools not listed in `tools` are `deny` (only for keys with a Claude Code equivalent).
- **opencode-only keys** (`question`, `lsp`, `websearch`, `external_directory`, `doom_loop`) are left unset — they have no Claude Code equivalent, so no restriction is invented.
- **Skills**: `skills: [a, b]` -> `skill: {"*": "deny", "a": "allow", "b": "allow"}`.
- **Unknown tools**: warned, skipped.
- **`mode`** defaults to `subagent` (Claude Code custom agents are subagents).

## Run after editing the source checkout

After changing shared configuration in the source checkout, re-run `sync` (or the relevant group). It is idempotent — unchanged artifacts report `unchanged`, changed ones update.

- **Skills** use native discovery. Pi reads command sources directly; Opencode commands are generated and need sync.
- **Derived files** (opencode's `AGENTS.md`/`agents/`/`opencode.json`, pi's `settings.json`/`CLAUDE.md`/`keybindings.json`, goose's `.goosehints`/`config.yaml`/`custom_providers/`) update on next `sync` run. So: edit rules/global.md → `sync` to refresh `AGENTS.md` (opencode), `CLAUDE.md` (pi), and `.goosehints` (goose).
