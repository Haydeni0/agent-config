# goose

Base config for [goose](https://goose.dev), synced into `~/.config/goose` by `settings-sync`.

## What's tracked

| File | Purpose |
|---|---|
| `config.yaml` | Base goose config (telemetry, extensions, search paths) |
| `custom_providers/*.json` | Custom provider definitions (OpenAI/Anthropic/Ollama compatible endpoints) |

## What goose reads natively (no sync needed)

goose has backward-compat discovery paths for `~/.claude`:

| Source | Goose discovers? | Path |
|---|---|---|
| `~/.claude/skills/` | Yes | `~/.claude/skills/` (compat path) |
| `~/.claude/agents/` | Yes | `~/.claude/agents/` (compat path) |
| `~/.claude/commands/` | No | goose slash commands are `config.yaml` entries mapping to recipe files (different format) |

Agent frontmatter note: goose only reads `name`, `description`, `model` from agent frontmatter. Claude Code keys (`tools`, `disallowedTools`, `skills`) are ignored - goose does not enforce tool restrictions from agent files.

## What settings-sync derives

| Source in the checkout | Target in `~/.config/goose` | Mechanism |
|---|---|---|
| `rules/global.md` + `@` imports | `.goosehints` | `@` imports inlined, `@skills/<n>` rewritten to `the \`<n>\` skill` (same transform as opencode `AGENTS.md` and pi `CLAUDE.md`) |
| `harnesses/goose/config.yaml` | `config.yaml` | copy; refuses to clobber a diverging file without `--force` (machine-specific settings set via `goose configure` or env vars are preserved) |
| `harnesses/goose/custom_providers/*.json` | `custom_providers/*.json` | per-file copy; orphans warned (removed with `--force`) |

## Usage

```bash
# explicit external dependency setup
agent-config bootstrap

# granular
agent-config sync goose            # all goose steps
agent-config sync goose hints     # .goosehints only
agent-config sync goose config     # config.yaml only
agent-config sync goose providers  # custom_providers/ only
```

After editing `rules/global.md` or `harnesses/goose/`, re-run `sync goose` (or `sync`).
