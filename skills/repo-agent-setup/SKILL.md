---
name: repo-agent-setup
description: Fold the agent-first kit (AGENTS.md, CLAUDE.md, MEMORY.md, backlog) into a repo - set up a repo for AI coding agents, or audit an existing setup. Trigger on "make this repo agent-friendly", "set up agent files for this repo", "repo agent setup", or an explicit /repo-agent-setup.
---

# repo-agent-setup

Decide which parts of this skill's kit a repo needs, ask a short grill,
fold them in, verify, report. Not every repo needs everything -
decisions are earned by signals, not assumed. Re-run switches to audit
mode: the skill is idempotent (maintains, never reinstalls).

## The kit (same directory as this file)

| File | Provisioned by this skill? | When |
|------|---------------------------|------|
| `AGENTS.md` | Always | Shape from template, substance from repo |
| `CLAUDE.md` | Always | One line: `@AGENTS.md` |
| `MEMORY.md` | Always | Seeded with the template's single example entry |
| `.agents/backlog.md` | Always | One convention, no overhead |
| `CONTRIBUTING.md` | Never | Manual reference only - create by hand if the repo's contribution model needs it |
| `README.md` | Never | The kit's own doc (tool-support matrix, what-goes-where, sources) - read it if the user asks why the kit is shaped this way |

**Read before anything else**: the `AGENTS.md` and `MEMORY.md` templates
in this skill's directory - they are the shape you will merge into and
the seed you will copy verbatim. Mode detection also depends on them
(a repo is template-shaped iff its AGENTS.md carries the Maintenance
section and its MEMORY.md carries this kit's frontmatter). Everything
below assumes you have their contents in context; re-read if unsure.

## Mode detection (first)

Scan for template shape: AGENTS.md carrying a Maintenance section
matching the `AGENTS.md` template in this skill's directory, and
MEMORY.md carrying the `MEMORY.md` template's frontmatter.

- **Absent → install mode** (the flow below).
- **Present → audit mode** (last section).

## Install mode

### 1. Deep scan

Read-only. Two sources, both mined: the repo tree AND the current
conversation - the user often invokes this right after working in the
repo, and their remarks, corrections, and the work just done carry
repo context the files don't (what the repo is for, what's dangerous,
what keeps going wrong). Fold conversation-derived context into the
same findings as file-derived.

Gather, in roughly this order:

- **Existing files**: AGENTS.md / CLAUDE.md / README / MEMORY.md /
  `.agents/` or legacy `.claude/` present? (drives create-vs-merge and the fold question)
- **Command surface**: Taskfile / Makefile / justfile / package.json
  scripts / pyproject / Cargo.toml / scripts dir - what exists, what
  the runner is
- **Docs inventory**: canonical docs (maxdepth ~2), what each answers
- **Repo shape**: size, top-level dirs, monorepo or single package
- **Infra greps**: `prod|deploy|sbatch|kubectl|terraform|systemd|cron`
  and similar - anything suggesting live systems or blast radius
- **Opener material**: README head, package description, key entry
  points, AND the conversation - enough to draft the
  one-fact-an-agent-gets-wrong opener. Read source entry points if
  neither supplies it; if you still can't draft a confident opener,
  that becomes grill Q1's fallback question.
- **Conversation context**: anything the user said in this
  conversation about the repo's purpose, dangers, conventions, or
  recurring pain - candidate opener lines, working rules, and
  working-rules question prompts. Cite it as conversation-derived in
  the findings report so the user can veto inference.

Do NOT grep TODOs/HACKs for rule proposals - a hotspot is one
occurrence, and rules are earned by repetition. Found issues are
backlog items, not instruction-file content.

### 2. Findings mini-report

One message, no questions yet: existing files found (and their
apparent state), command surface detected, docs found, infra signals
on/off, proposed section set. This is the evidence the grill's
questions hang from - keep it tight.

### 3. Sequential grill

Grill-me mechanics: one **Q[N]** at a time, options with an explicit
**Recommend:**; `yes/ok` accepts the recommendation, free text
overrides. Plain chat text, never modal tools. Fixed order:

1. **Opener** - show the draft; "correct?" (if you couldn't draft
   one: "what's the one fact an agent would get wrong about this
   repo?")
2. **Working rules** - iff the fold found existing rules: show them,
   propose which to keep. Always end with: "and what would an agent
   get wrong here that hasn't been said?" - the user's knowledge is
   the other rule source
3. **Danger** - always asked: "any live infra / anything dangerous
   here?" A yes earns a **Working rule** (e.g. "never restart X"), a
   named Safety section is NOT created - the user adds one by hand
   from the AGENTS.md template when a repo warrants the full
   detection-command shape
4. **Autonomy** - always asked: "will unattended/long runs happen
   here?" No → section cut. Yes → write fork definition + 3-tier
   table (decide-and-note / queue-to-backlog / stop) from the
   Autonomy section of this skill's `AGENTS.md` template
5. **CLAUDE.md fold** - iff a fat CLAUDE.md was found: "fold into
   AGENTS.md and leave the one-line import?" (default on yes: fold -
   repo wording wins on substance, template shape holds, anything
   stale gets flagged not silently fixed)

Announce these as decisions in the mini-report (scan is unambiguous;
correct in passing if wrong, don't ask):

- Documents map (docs found → table with one "answers" line each)
- Commands section (written in the repo's own runner vocabulary -
  never hardcoded to a specific toolchain; iff a command surface
  exists; cut if none does)
- MEMORY.md + backlog.md creation

### 4. Apply

- Merge the repo's substance into the shape of this skill's
  `AGENTS.md` template - template wins on **shape**, repo wording
  wins on **substance**. Never delete earned wording; flag stale
  content (dead commands, dead paths, wrong claims) in the report -
  don't silently fix it.
- Every placeholder bracket in the template filled or its section
  cut. A section with no content gets cut, never kept as scaffolding.
- Land: AGENTS.md (from the template), CLAUDE.md (copy this skill's
  `CLAUDE.md` verbatim - it is exactly the import line), MEMORY.md
  (copy this skill's `MEMORY.md` template verbatim: frontmatter +
  example entry), `.agents/backlog.md` (create per the backlog
  skill's template if that skill is available; otherwise a `# Backlog`
  header with an `## Open` section) - repo root and `.agents/` only.
  Never touch `.claude/settings.json`, never scaffold `.agents/plans/`.
- Workflow docs (requirements / decisions / questions / progress) are
  NOT provisioned - they emerge from workflows (dev-cycle writes its
  own artifacts; a QUESTIONS.md appears the first time something
  needs queuing). The Documents map records what exists.
- Stage with `git add` for review. No commits unless the repo's
  authorization stance allows and the task prompt calls for it.

### 5. Self-verify (mechanical, before reporting done)

- No template placeholders survive (`grep '<' AGENTS.md` returns
  nothing placeholder-shaped)
- No empty sections (every heading has content or is gone)
- CLAUDE.md is exactly the import line
- MEMORY.md has frontmatter + the example entry
- README does not duplicate AGENTS.md rules
- Every decision from the grill is reflected in the files

### 6. Report

Decision table - one line per file: created / merged / cut / flagged.
Plus: the staged diff as evidence, stale-content flags, and anything
the user should add by hand later (CONTRIBUTING if the contribution
model ever needs it, Safety if danger grows beyond a working rule).

## Audit mode (re-run on a template-shaped repo)

The same admission test the kit's Maintenance section states, applied
to the files themselves:

- **Admission test**: for each line, "would removing this cause a
  mistake?" Propose cuts for anything derivable from code,
  linter-enforced, standard convention, or describing code that has
  since changed (stale rules are worse than no rules).
- **Staleness**: do the Commands still run? Do the Documents-map
  targets still exist? Do the Working rules still match the code?
  Check by running/reading, not by assuming.
- **MEMORY.md prune**: merge or drop entries whose constraint no
  longer holds; promote stabilized learnings into AGENTS.md rules.
- Propose all changes via a short grill (one Q at a time, same
  mechanics), apply on acceptance, verify, report.

Never widen scope in audit mode - no new sections beyond what the
repo earned, no workflow docs, no settings.json.

## Existing project documents

Use the global legacy-document rule before creating or resuming plans/backlogs: canonical `.agents` when present, legacy `.claude` when it is the only copy, reconcile both before resuming, editing, or migrating. Preserve IDs and checkbox progress.
