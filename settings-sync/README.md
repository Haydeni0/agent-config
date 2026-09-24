# settings-sync

Syncs the agent-config source checkout into opencode, pi, goose, agy, Codex, and no-mistakes. The source checkout owns the managed artifacts listed below; each harness keeps its own local state.

`~/gitrepos/agent-config` is your git repo - `git pull` on any machine, then `sync`. Shared skills and commands use each harness's native discovery where available; the tables below identify the artifacts that need conversion.

## What it syncs

### Claude

Shared `harnesses/claude/settings.json` merges into the native settings file. `rules/global.md` becomes global `CLAUDE.md` with source routing. Shared skills, commands and agents are installed as individual links; local skill containers remain in place. Compatibility links for hooks, custom plugins and launcher resources are listed in [migration](../docs/migration.md#compatibility-links). `--claude-home` selects a custom Claude runtime destination and renders hook commands accordingly.


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
| `skills/` | (native) | codex reads `~/.agents/skills`, which local sync links to `~/.claude/skills`; inspect discovery with Codex's `/skills` |

Commands, hooks, and plugins are not bridged - codex uses different formats. See [`harnesses/codex/README.md`](../harnesses/codex/README.md).

Codex config tables merge recursively. The template owns the keys it declares; local keys, including project trust, hook approvals, and UI state, create no drift. Removing a template key leaves its installed value in place. Invalid TOML fails before writing. Use `--codex-dir` to target a custom `CODEX_HOME`.

## Usage

```bash
# In the examples below, `sync` is the invocation from Run above, i.e.
# `uv run --directory ~/gitrepos/agent-config/settings-sync sync` (or your `ssync` alias).

# sync everything (opencode + pi + goose + agy + codex + no-mistakes); refuse on conflict, exit 1 if any conflict
sync
sync all                       # explicit

# per tool
sync opencode                  # all opencode steps
sync pi                        # pointers + inlined context
sync goose                     # hints + config + providers
sync agy                       # rules + skills
sync codex                     # shared defaults + global AGENTS.md -> ~/.codex
sync no-mistakes               # config template + machine overlay -> ~/.no-mistakes
sync opencode config           # one step (config|tui|agents-md|agents|commands|plugins|skills)
sync pi config                 # one step (config|context|keybindings)
sync goose config              # one step (hints|config|providers)
sync agy agents-md             # one step (agents-md|skills)
sync codex config              # one step (config|agents-md)
sync no-mistakes config        # one step (config)

# flags (accepted before or after group/subcommand)
sync --dry-run                 # preview, write nothing
sync agy --check               # exit nonzero on drift, write nothing
sync goose --force             # clobber diverging derived files
sync --verbose                 # show diffs for changed text artifacts
sync --pi-dir /tmp/glm-pi pi   # target a different pi agent dir
```

Common flags (`--force`, `--dry-run`, `--check`, `--verbose`) work anywhere in the command line (e.g. `sync --check agy`, `sync agy --check`, or `sync agy settings --force`). Path override options (`--claude-dir`, `--opencode-dir`, `--pi-dir`, `--goose-dir`, `--agy-dir`, `--agy-cli-dir`, `--nomistakes-dir`, `--codex-dir`) go before the tool subcommand.

## Install and commands

```bash
uv tool install --editable ./settings-sync
agent-config sync                 # local settings and links
agent-config sync codex            # one harness
agent-config sync codex agents-md  # one output
agent-config check codex           # read-only drift check
agent-config doctor codex          # paths, sources, links, host availability
agent-config bootstrap pi          # explicit package installation
agent-config bootstrap --dry-run   # show selected installed hosts
```

Run the install command from the repo root. Python dependency changes require refreshing the editable tool environment. Lockfile-based alternative: `uv run --locked --directory settings-sync agent-config`.

Legacy `sync [harness] [step]` stays available. `sync.sh` is a compatibility entry for bootstrap. Bootstrap defaults to installed hosts; no-mistakes requires explicit selection because installation starts its daemon. Pi packages have exact versions/revisions in `harnesses/pi/settings.json`; web-access uses `npm ci`. Evo CLI/plugin and initial no-mistakes release pins live in `scripts/bootstrap.sh`. Native no-mistakes updates remain user-controlled.

Source resolution: `--source` (alias `--claude-dir`), then `AGENT_CONFIG_REPO`, then `source = "/absolute/repo"` in `$XDG_CONFIG_HOME/agent-config/config.toml`; an unconfigured source is an error. Native destinations are resolved per invocation; explicit destination flags beat `CODEX_HOME`, `OPENCODE_CONFIG_DIR`, and XDG defaults. Path flags go before the subcommand.

## Ownership and recovery

Shared templates own the keys they declare. JSON/YAML/TOML mappings merge recursively; declared arrays/scalars replace; omitted keys stay local. Invalid source or installed config fails before writing. Codex retains TOML formatting. no-mistakes retains its explicit template-plus-overlay contract.

Generated instructions, commands, agents, providers, and links use `$XDG_STATE_HOME/agent-config/managed.json` (default `~/.local/state/agent-config/managed.json`). Identical existing outputs can be adopted. Unchanged managed outputs update normally; local edits cause conflicts. Selected-step `--force` backs up a conflicting file before replacement under the adjacent `backups/` directory, with a JSON record of its original destination. Restore that file to its recorded destination if needed.

Cleanup deletes only unchanged recorded outputs. Foreign files and real directories survive force; changed managed orphans remain conflicts. Checks and dry runs preserve config, links, ownership records, and timestamps. Installs use atomic replacement and detect edits since reading; advisory locks serialize generated-output writes, while native applications can still write their own settings.

The shared `~/.agents/skills` link is installed during Codex/full local sync. A foreign directory/link is reported and preserved, including with force. Inventory and reconcile its contents before replacing it deliberately.

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
