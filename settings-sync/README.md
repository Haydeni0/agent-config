# settings-sync

Syncs `~/.claude` config into opencode, pi, goose, agy, Codex, and no-mistakes. `~/.claude` owns the managed artifacts listed below; each harness keeps its own local state.

`~/.claude` is your git repo - `git pull` on any machine, then `sync`. Shared skills and commands use each harness's native discovery where available; the tables below identify the artifacts that need conversion.

## What it syncs

### opencode

| Source in `~/.claude` | Target in `~/.config/opencode` | Mechanism |
|---|---|---|
| `opencode/opencode.json` (base config) | `opencode.json` | passthrough, adds `$schema` |
| `opencode/tui.json` (TUI config) | `tui.json` | passthrough, adds `$schema` |
| `opencode/rules.md` (opencode-only rules) | appended to `AGENTS.md` | safety rules appended after CLAUDE.md content |
| `CLAUDE.md` | `AGENTS.md` | `@skills/<n>` rewritten to `the \`<n>\` skill` |
| `agents/*.md` | `agents/*.md` | frontmatter transform (see below) |
| `commands/` | `commands` | relative symlink |
| `plugins/cache/.../superpowers/<v>/.opencode/plugins/superpowers.js` | `plugins/superpowers.js` | relative symlink, highest semver resolved |
| `skills/` | (native) | opencode reads `~/.claude/skills` directly; tool validates only |

Hooks (`hooks/`) are not bridged — opencode's plugin hook model differs. Recreate as an opencode plugin if needed.

### pi

| Source in `~/.claude` | Target in `~/.pi/agent` | Mechanism |
|---|---|---|
| `pi/settings.json` (pointer template) | `settings.json` | **wholesale copy** (template is SOT; pi's own keys are disposable) |
| `pi/keybindings.json` (optional) | `keybindings.json` | **wholesale copy** (SOT; pi falls back to defaults if absent) |
| `CLAUDE.md` | `CLAUDE.md` | `@skills/<n>` rewritten (pi can't expand `@` refs) - skills/commands read directly (via pointers), tool validates only |
| `skills/` | (native) | pi reads `~/.claude/skills` directly (via pointers); tool validates only |
| `commands/` | (native) | pi reads `~/.claude/commands` directly (via pointers) |

pi's `settings.json` is **wholesale-copied** (no merge, no preserved machine keys): `lastChangelogVersion` and other pi-owned state self-heal on next pi run. Per-machine model/auth/provider choices belong in `auth.json`/`models.json`/env, not `settings.json`. See [`pi/README.md`](../pi/README.md).

### goose

| Source in `~/.claude` | Target in `~/.config/goose` | Mechanism |
|---|---|---|
| `CLAUDE.md` | `.goosehints` | `@skills/<n>` rewritten (same transform as opencode `AGENTS.md`) |
| `goose/config.yaml` (base config) | `config.yaml` | copy; refuses to clobber diverging without `--force` (preserves machine-specific settings) |
| `goose/custom_providers/*.json` | `custom_providers/*.json` | per-file copy; orphans warned (removed with `--force`) |
| `skills/` | (native) | goose reads `~/.claude/skills` directly via compat path; tool validates only |
| `agents/` | (native) | goose reads `~/.claude/agents` directly via compat path; tool validates only |

goose discovers skills and agents from `~/.claude` natively (backward-compat paths). Agent frontmatter: goose only reads `name`/`description`/`model` - Claude Code keys (`tools`/`disallowedTools`/`skills`) are ignored. Commands are not synced (goose slash commands use a different format - `config.yaml` entries mapping to recipe files). See [`goose/README.md`](../goose/README.md).

### agy

| Source in `~/.claude` | Target | Mechanism |
|---|---|---|
| `gemini/settings.json` | `~/.gemini/antigravity-cli/settings.json` | copy; refuses to clobber diverging without `--force` |
| `CLAUDE.md` | `~/.gemini/config/AGENTS.md` | `@skills/<n>` rewritten to `the \`<n>\` skill` |
| `skills/` | `~/.gemini/config/skills/` | relative symlink per skill directory; orphans warned (removed with `--force`) |

`agy` (Antigravity) reads agent settings from `antigravity-cli/settings.json`, global rules from `AGENTS.md`, and discovers custom skills from `skills/`.

### no-mistakes

| Source in `~/.claude` | Target in `~/.no-mistakes` | Mechanism |
|---|---|---|
| `no-mistakes/config.yaml` (template, shared keys) | `config.yaml` | deep-merged with the overlay, then written |
| `no-mistakes/config.local.yaml` (overlay, machine/local keys incl. `agent`, untracked) | `config.yaml` | overlay wins at leaf level |

Fully derived, pi-style: regenerated on every sync with no force gate, so hand edits to `~/.no-mistakes/config.yaml` die on the next sync. Which key goes in the template vs the overlay, template rules, agent switching, and update flow live in [`no-mistakes/README.md`](../no-mistakes/README.md). This target manages **only** `config.yaml` - everything else in `~/.no-mistakes` (binary, daemon state, db, worktrees, evidence) is untouched.

### codex

| Source in `~/.claude` | Target in `~/.codex` | Mechanism |
|---|---|---|
| `codex/config.toml` | `config.toml` | merge declared defaults; preserve local keys and formatting; plain `codex` loads them |
| `CLAUDE.md` | `AGENTS.md` | `@skills/<n>` rewritten (same transform as opencode's AGENTS.md) |
| `skills/` | (native) | codex reads `~/.agents/skills`, which sync.sh symlinks at `~/.claude/skills`; inspect discovery with Codex's `/skills` |

Commands, hooks, and plugins are not bridged - codex uses different formats. See [`codex/README.md`](../codex/README.md).

Codex config tables merge recursively. The template owns the keys it declares; local keys, including project trust, hook approvals, and UI state, create no drift. Removing a template key leaves its installed value in place. Invalid TOML fails before writing. Use `--codex-dir` to target a custom `CODEX_HOME`.

## Usage

```bash
# In the examples below, `sync` is the invocation from Run above, i.e.
# `uv run --directory ~/.claude/settings-sync sync` (or your `ssync` alias).

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

## Run

Stateless — no install step, just run it from the repo each time (needs [uv](https://docs.astral.sh/uv/)):

```bash
uv run --directory ~/.claude/settings-sync sync          # sync everything (opencode + pi + goose + agy + codex + no-mistakes)
uv run --directory ~/.claude/settings-sync sync opencode # granular
uv run --directory ~/.claude/settings-sync sync pi       # granular
uv run --directory ~/.claude/settings-sync sync goose    # granular
uv run --directory ~/.claude/settings-sync sync agy      # granular
uv run --directory ~/.claude/settings-sync sync codex    # granular
uv run --directory ~/.claude/settings-sync sync no-mistakes # granular
# tip: alias ssync='uv run --directory ~/.claude/settings-sync sync' for brevity
```

No persistent install, no shim on PATH — `git pull` and you're on the latest version. (If you prefer a global command, `uv tool install ~/.claude/settings-sync` puts `sync` on PATH, but you must reinstall to update.)

## Conflicts and safety

- By default the tool **refuses to delete or overwrite** anything it didn't create. A conflicting real file/dir at a managed path is skipped with a warning.
- `--force` removes/replaces conflicting managed paths, reconciles orphaned agent files (target `.md` not in source), and retargets wrong symlinks.
- No files are deleted without `--force`.
- **Exception — pi config:** `settings.json` is always overwritten (wholesale copy; the template is SOT). `--force` is not needed for it.
- **Codex defaults:** template keys are merged into `config.toml` on every sync, preserving other keys and formatting. `AGENTS.md` keeps the normal force gate.
- opencode manages only: `opencode.json`, `tui.json`, `AGENTS.md`, `agents/`, `commands`, `plugins/superpowers.js`. Everything else in `~/.config/opencode` is left untouched.
- pi manages only: `settings.json`, `keybindings.json`, `CLAUDE.md`. Everything else in `~/.pi/agent` (auth, sessions, bin, models.json) is left untouched.
- goose manages only: `.goosehints`, `config.yaml`, `custom_providers/`. Everything else in `~/.config/goose` (sessions, permission.yaml, secrets.yaml, prompts/) is left untouched.

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

## Run after editing `~/.claude`

After changing anything in `~/.claude`, re-run `sync` (or the relevant group). It is idempotent — unchanged artifacts report `unchanged`, changed ones update.

- **Skills/commands** are read directly by both tools — editing them needs only a `/reload` in pi (opencode picks them up live via symlink), no re-sync required.
- **Derived files** (opencode's `AGENTS.md`/`agents/`/`opencode.json`, pi's `settings.json`/`CLAUDE.md`/`keybindings.json`, goose's `.goosehints`/`config.yaml`/`custom_providers/`) update on next `sync` run. So: edit CLAUDE.md → `sync` to refresh `AGENTS.md` (opencode), `CLAUDE.md` (pi), and `.goosehints` (goose).
