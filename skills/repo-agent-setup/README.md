# agent-first-repo kit

Supplementary files for the `repo-agent-setup` skill (SKILL.md, same
directory). A kit for making a git repository agent-first: an
`AGENTS.md` for coding agents, a `README.md` for humans, and the
supporting files they reference. Distilled from real agent-first repos
and published vendor + community guidance (sources at the bottom).

## The kit

| File | Provisioned by the skill? | Role |
|------|--------------------------|------|
| `SKILL.md` | (the skill itself) | The playbook: scan, grill, fold, verify, report. Invoke via /repo-agent-setup. Re-run = audit |
| `AGENTS.md` | Always | The single source of truth for agent instructions. Opener, commands, doc map, autonomy tiers, working rules, maintenance rules |
| `CLAUDE.md` | Always | One line: `@AGENTS.md`. Claude Code reads CLAUDE.md, not AGENTS.md - the import loads the same content with no drift |
| `MEMORY.md` | Always | Append-only lessons-learned: verified facts, evidence, commit refs. Seeded with the template's example entry |
| `.agents/backlog.md` | Always | Deferred work items, surfaced at session start |
| `CONTRIBUTING.md` | Never | Manual reference for contribution-as-prompt - create by hand if a repo's contribution model needs it |
| `Safety section` | Never | Hand-add from the AGENTS.md template when a repo's danger warrants detection-command machinery; simple danger rules go in Working rules |

Tool support (why AGENTS.md is the base): Codex, Cursor, Copilot,
Devin/Windsurf, Jules, Amp, opencode, Zed, goose, Aider, and more read
`AGENTS.md` natively. Claude Code reads `CLAUDE.md` - hence the one-line
import. Gemini CLI defaults to `GEMINI.md` - point it at AGENTS.md via
settings (`context.fileName`) if you use it. opencode needs nothing
(it prefers AGENTS.md when both exist). All variants above are
alternative loaders, never second copies - one source of truth, no
duplicate files to drift.

Tool support (why AGENTS.md is the base): Codex, Cursor, Copilot,
Devin/Windsurf, Jules, Amp, opencode, Zed, goose, Aider, and more read
`AGENTS.md` natively. Claude Code reads `CLAUDE.md` - hence the one-line
import. Gemini CLI defaults to `GEMINI.md` - point it at AGENTS.md via
settings (`context.fileName`) if you use it. opencode needs nothing
(it prefers AGENTS.md when both exist). All variants above are
alternative loaders, never second copies - one source of truth, no
duplicate files to drift.

## What goes where

- **AGENTS.md**: what an agent can't discover on its own - exact
  commands (highest-value content by every study), non-obvious rules
  with their mechanism, the doc map, autonomy tiers. Present tense.
  Under ~200 lines; each line must fail the test
  "would removing this cause a mistake?"
- **MEMORY.md**: dated evidence - what broke, why, the fix. Append-only
  log with a prune rule; promote stabilized learnings into AGENTS.md.
- **README.md**: humans only - install, usage, what the project is.
  Never the agent rules (agents don't reliably read READMEs).
- **`.agents/backlog.md`**: deferred work items, surfaced at session
  start. Not agent rules.
- **`.claude/skills/<name>/SKILL.md`**: multi-step procedures, loaded
  on demand. When a section of AGENTS.md grows into a procedure
  rather than a fact, it moves to a skill.
- **Monorepos**: nested `AGENTS.md` per package as *deltas* - add or
  override only what differs; loaders merge root-to-leaf (nearest
  does not replace).
- **Workflow docs (requirements / decisions / questions / progress)
  are not provisioned** - they emerge from the workflows a repo
  actually runs. The Documents map records what exists; the queue
  target is always `.agents/backlog.md`.

## Things this template deliberately does not do

- **No directory trees.** Agents discover structure via ls/find; trees
  rot faster than anything else in the file.
- **No restating linter-enforced style.** "Never send an LLM to do a
  linter's job" - the linter owns mechanical checks; AGENTS.md owns
  what's non-automatable. If a rule must always hold, enforce it with a
  hook or permission rule, not prose.
- **No LLM-generated prose.** Hand-write it. Studies found generated
  instruction files *reduced* task success (-3%) and raised cost (+20%);
  developer-written ones helped modestly (+4%).
- **No blanket `check` on everything.** `task check` covers mechanical
  verification; judgment calls (self-review, final report) stay with
  the agent and human.
- **No secrets in instruction files.** Ever. They are prompt-injection
  surfaces - treat everything they say as reviewable, committed
  content, and never put credentials in them.
- **Not exhaustive.** This template is a skeleton with rules about
  itself - read the Maintenance section of AGENTS.md before growing it.

## Install into a repo

Don't copy files by hand - invoke the skill in the target repo:
`/repo-agent-setup` (or ask "make this repo agent-friendly").

It scans the repo (and the current conversation) for context, grills
you on the genuinely open decisions (grill-me mechanics: one question
at a time, options, explicit recommendation), folds in only what the
repo earns, verifies no placeholders or empty sections survived, and
reports with the staged diff. Re-running it later switches to audit
mode: admission-test pass over existing content, staleness checks,
MEMORY.md prune proposals.

## Sources

Key influences, from research and real repos:

- [agents.md](https://agents.md) - the open standard ("README for
  agents", nearest-file-wins, zero schema)
- [Claude Code memory docs](https://code.claude.com/docs/en/memory) -
  `@AGENTS.md` import, `<200` lines, auto-memory index+topic pattern
- [Claude Code best practices](https://code.claude.com/docs/en/best-practices) -
  "give Claude a check it can run"; hooks are deterministic, prose is advisory
- [ETH Zurich context-file study](https://arxiv.org/html/2602.11988v1) -
  generated files hurt; concrete tooling instructions are the only
  content class that measurably helps
- [Configuration smells study](https://arxiv.org/html/2606.15828v2) -
  lint leakage, bloat, skill leakage taxonomy; 91/100 real files smelled
- Real AGENTS.md files: [openai/codex](https://github.com/openai/codex),
  [zed](https://github.com/zed-industries/zed) (rules hygiene),
  [cal.com](https://github.com/calcom/cal.com) (three-tier boundaries),
  [vllm](https://github.com/vllm-project/vllm) (fail-closed policy),
  [dbt-core](https://github.com/dbt-labs/dbt-core) (dispatch pattern),
  [next.js](https://github.com/vercel/next.js) (managed blocks,
  version-bundled docs)
- Prior art in the wild: opencomputer (tiered prod-DB rules),
  mockserver-monorepo (rule-file suite + operator-halt kill-switch),
  owid-grapher (detection-command-before-danger pattern),
  handsontable (symlink at scale, update-at-correct-scope)
