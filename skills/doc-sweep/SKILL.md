---
name: doc-sweep
description: Use when a repo's accumulated agent docs need a retrospective tidy - session notes, handoffs, scratch files, stale plans/specs, historical records, and living reference docs piling up across docs/, root, or .claude/. Triggers include "sweep the docs", "tidy up the docs/notes", "audit our docs", "which of these can we archive", "the notes in this repo are a mess", "doc rot". Not for reformatting one messy doc for readability (doc-reformat), starting or resuming a living doc (living-doc), writing a spec or plan (write-spec / writing-plans), parking a work item (backlog), or trimming tests (test-trim).
deps: [doc-reformat]
argument-hint: "[path|dir] (optional scope)"
---

# doc-sweep

Repo-wide, retrospective tidy of agent-generated docs. Audit every doc, report
capped numbered findings, mutate **only what the human approves**. Read-only
until the gate.

Everything else in the ecosystem operates on one doc or one flow in the
present task. doc-sweep is the only repo-wide, class-driven, retrospective pass.

## Scope

All repo markdown except:

| Excluded | Detect via |
|---|---|
| Product/user-facing docs | publication plumbing (mkdocs.yml, docusaurus, sphinx, vitepress, CI deploying docs/), standards filenames (README, CHANGELOG, SECURITY, CONTRIBUTING, LICENSE), content addressing the software's *user* not its *builder* |
| Vendored/generated | `node_modules/`, `.venv/`, `site-packages/`, any `.gitmodules` path, "auto-generated"/"DO NOT EDIT" banners |
| Managed ADRs | `adr/`/`decisions/` with numbered records - at most a `status: superseded` line, never content |
| Instructions | SKILL.md, CLAUDE.md, AGENTS.md bodies - audited as evidence, config-semantics edits belong to agent-config |

Ambiguous file = out of scope, named in the report ("excluded, appears stale").
A false exclusion costs a report line; a false inclusion damages user docs.

`$ARGUMENTS` path/dir = run the full pipeline scoped to it. Single file is
fine - intent here is lifecycle state, not readability.

## Classes

Exactly one class per doc (a doc that is both is the rot):

- **living** - source of truth about today (reference, methodology, runbook). Fixable in place.
- **snapshot** - dated record of a moment (session notes, handoffs, specs, plans, postmortems, anything in history/old/archive dirs). Immutable: banners at most.
- **scratch** - disposable working notes. Report-only (see Untracked rule).
- **mixed** - living methodology + appended dated log in one file. Default action: EXTRACT.

Decision order: location/dir name > top-of-file content > filename date >
frontmatter status. **Frontmatter lies** (`docs/old/` files say `status:
verified`); location and top-of-file banner outrank it. Plain reference doc
with no signals = living.

## Convention deference

First move: read the repo's own convention docs - lifecycle skills in
`.claude/skills/`, CLAUDE.md/AGENTS.md/README doc maps. Adopt the repo's
vocabulary (its status words), locations (its archive dirs), and disposal
targets. If the repo's convention conflicts with this skill's defaults, the
convention wins on *where things go and what they're called*; the Never-list
below wins on *safety*. The conflict itself is a FLAG.

Most proposals should read as "enforce your own rules" - easy approvals.

## Phases

### 1. Inventory (mechanical, everything)

```bash
git ls-files '*.md'; git ls-files --others --exclude-standard '*.md'
git check-ignore <paths>          # ignored = report-only tier
git log -1 --format=%cs -- <file> # last touch
grep -rn '<filename>' --include='*.md' .   # inbound refs (from live files only)
```

Per file: path, lines, class, tracked?, inbound refs. Untracked files with no
archive convention → one question at the gate, only if archive/extract
findings exist (default `docs/archive/`, or the repo's existing archive dir).

### 2. Audit (mechanical first; read living + mixed only)

Mechanical checks, every doc:
- Tracked doc referencing an untracked/ignored path (dangles on fresh clone)
- Stale file/script/env refs in living docs (`test -e`, grep)
- Living doc contradicting repo state (grep the referenced config/source)
- Unbounded growth: mixed doc with dated entries - split at the
  self-declared era boundary: entries from before it extract, current-era
  entries stay
- Rules-file drift: tables/counts/commands vs reality (skills table vs `.claude/skills/`, cited commands that cannot run)
- Byte-identical duplicates (`cmp`)

Then read living + mixed docs (never snapshots - a wrong diagnosis with a
correction banner is the *healthy* end state, not rot). >10 content-read docs
or >120KB total → dispatch read-only subagents per doc, returning findings
records only, never doc bodies.

Untracked/ignored files: inventory them, report risk (no git history, no
backup), never propose or apply an action unless the human names it - even
when the repo's own lifecycle mandates a promotion. Untracked scratch is the
owner's intent; violating it beats stranding findings.

### 3. Report (chat, capped)

```
## Doc sweep - <repo>, <date>

Inventory: N docs - a living, b snapshot, c mixed, d scratch (e untracked/ignored).
Required reading: X lines across living docs.

### Findings
N. ACTION - path [mechanical|judgment]
   Evidence quote. -> proposed change (diff for FIXes)

### Key decisions (named-only; never under "apply all")
K. ...

### Excluded / healthy
- ...

### Gate
Apply which? "apply all" (ordinary only), numbers, or key-decision numbers by name.
```

Cap: **10 ordinary findings**, ranked by required-reading lines saved + rot
severity; key-decision findings exempt from the cap. Overflow → one-line
backlog entries. Evidence tier on every finding: `[mechanical]` (grep/git
output) or `[judgment]` (reading; budget human review there).

### 4. Gate (chat text, not modals)

Two classes:
- **Ordinary**: ARCHIVE, EXTRACT, MARK, mechanically-verified FIX. Rides under "apply all".
- **Key**: anything touching rules files (README/AGENTS.md/CLAUDE.md
  tables/counts - mechanical fixes only, never rule semantics), DELETE,
  untracked/ignored-file actions. Named individually, even inside "apply all".

Amendment that narrows an action ("2 but keep the 08-15 entry") → re-print the
amended finding, one confirm, then apply. Pure selections execute directly.

The report ends the turn. Apply starts only on the user's next message.

### 5. Apply (next turn, from the report)

1. Clean-tree guard (`git status`); dirty → ask. Per-file: anything changed
   since audit → skip and report, never overwrite.
2. Moves first (`git mv`, no content change), then edits - pure renames stay
   pure. EXTRACT is byte-verbatim (doc-reformat's verbatim contract); entry
   moves to `<archive>/<stem>-<oldest>-to-<newest>.md`, pointer line left.
3. Banners: strict 2 lines (status + pointer). Long context belongs in the
   successor doc, never the banner.
4. Frontmatter `status:` on acted-on files only (never repo-wide retrofit);
   use the repo's vocabulary if it has one.
5. Update inbound links (grep old paths across live docs).
6. Dispatch a fresh-context reviewer subagent (below). FAIL findings return
   to the human before staging. Do not self-certify the apply.
7. Verify: old-path grep zero hits outside archive, links resolve,
   before/after required-reading count. `git add`, never commit.

### Fresh-context reviewer (mandatory, before staging)

The agent that applied the changes is the worst judge of them - it shares
the apply's blind spots. Dispatch one read-only subagent that sees the work
cold. It gets: the approved report, the diff (`git diff HEAD` + `git
status`), the pristine baseline (`git show HEAD:<path>`), and this skill's
Never-list. It checks, each PASS/VIOLATION with file + evidence:

1. Scope - every diff hunk maps to an approved finding; nothing extra,
   nothing missing
2. EXTRACT byte-verbatim vs `git show HEAD:<master>` (the extracted range)
3. Snapshot bodies byte-identical to HEAD except authorized banner/frontmatter
4. FIX diffs are exactly what the report showed
5. Untracked/ignored files unchanged - git has no baseline for these, so
   verify via mtime (inside the apply window?) and content that references
   this run
6. Approved deletes happened, and only those
7. Links in changed files resolve; old-path grep clean

Its FAIL blocks staging. Violations go back to the human with the
reviewer's evidence; the human decides revert (git checkout) or accept.

## Actions

| Action | On | Rule |
|---|---|---|
| FIX | living | Mechanically-verified facts only (dead path, count, checkable status) - diff shown. Judgment stays FLAG. |
| EXTRACT | mixed | Move dated entries byte-verbatim to archive, leave pointer |
| ARCHIVE | living/snapshot | `git mv` to repo's archive dir + 2-line banner + `status:` |
| MARK | snapshot | Banner/frontmatter only, no move, no content - only when its status reads wrong; a terminal record already correctly filed needs nothing |
| FLAG | any | Needs human judgment - both sides quoted, no proposed fix |
| DELETE | tracked byte-identical dupes only | Key class; untracked files are never deleted |

## Never-list

- Never mutate before the gate - no "obvious" fix slips through.
- Never rewrite snapshot bodies; never resolve a load-bearing contradiction
  silently (FLAG it).
- Never edit content of untracked/ignored files.
- Never delete untracked/gitignored files, or anything not byte-identical-tracked.
- Never prose-rewrite a living doc where a mechanical fix suffices - FIX is
  surgical, shows a diff.
- Never touch product docs, vendored/generated docs, changelogs, managed ADRs.
- Never write report/state files into the repo; no audit log, no frontmatter retrofit.
- Never run project code to verify claims; static checks only.
- Never commit or push.

## Idempotency

No state files. The docs are the state: each run re-derives everything, and
applied actions leave mechanically visible postconditions (file in archive dir
with banner, entries gone from master, fixed paths exist) - the next run sees
"correctly filed" and skips. Stored `status:` is a signal, not truth.

## Common mistakes

| Mistake | Fix |
|---|---|
| Rewriting an archived doc's wrong diagnosis | Wrong-with-banner is the healthy end state. MARK at most. |
| Deleting the era-doc or shipped plan | Archive, don't delete - the record outranks tidiness |
| "Improving" a living doc's prose while fixing one path | FIX is the diff shown in the report. Nothing else. |
| Trusting `status: verified` frontmatter | Location + top-of-file banner outrank frontmatter |
| Flagging every orphan | Orphan only matters for living docs; dated records are legitimately unlinked |
| Report dumped into a file | Chat, capped. Files rot; the backlog catches overflow |
| Acting on an untracked scratch "to rescue it" | Report the risk; the human names the action |
| Punting a stale-status finding to FLAG because the fix touches a few lines | If repo state mechanically decides the truth (config value, file existence, count), it is a FIX - show the surgical diff. FLAG only when evidence cannot say which side is right. |
| Asking where archives go on a clean run | Only when archive/extract findings exist and no convention detected |
| Self-certifying the apply ("verified my own changes, all green") | The applier shares its own blind spots. Fresh-context reviewer is mandatory before staging |
