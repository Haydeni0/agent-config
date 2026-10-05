# AGENTS.md - <repo name>

Guidance for AI coding agents (Claude Code, Codex, Cursor, opencode, ...)
working in this repository. Read at session start.

[What this repo is, in terms an agent needs - not marketing. Include the one
architectural fact a newcomer would get wrong without being told (e.g. "cw is
read-only: it renders CLI JSON output and writes nothing to the cluster").
1-3 sentences.]

## Commands

The command surface is the contract: agents run these and act on the
result. [Written in THIS repo's own runner - Taskfile, make, just,
package.json scripts, cargo, whatever the repo actually uses. Never
transplant another toolchain's vocabulary here. Keep a single aggregate
"claim it's green" command if the repo has enough surface for one.]

```bash
<install command>        # deps
<fast test command>      # iterative suite - run after every edit
<full test command>      # full local suite
<check command>          # the "claim it's green" gate
```

[Which suite to run when: the fast suite is the default habit; the full
suite is the exception - name the areas whose bugs only the slow suite
catches. Cut if the repo has one suite.]

[Optional - commands deliberately NOT provided and why: prod or
destructive actions stay user-owned, not one command away from an
agent. If nothing here applies, cut this paragraph. This section is cut
entirely if the repo has no command surface.]

## Working rules

[Only the non-obvious - what an agent would get wrong by following defaults
or training-data habits. Each rule: the behavior + the one-line mechanism
that makes it true. Bad: "write clean code". Good: "never hardcode QoS
names into a renderer - a config change silently renders them white;
derive distinctions from data the CLI exposes". One bullet per rule.
Repo-specific git conventions, if any, live here as ordinary rules -
not a named section. Danger rules of the simple kind ("never restart
X", "don't touch Y while Z is live") also live here. Cut this section
entirely if the repo has no such rules yet - rules are added when a
mistake repeats, not up front.]

[Optional - iff a binding requirements contract was chosen in
repo-agent-setup. If not chosen, cut this block:]

- Update the canonical requirements document before or with every
  user-visible behavior change.
- Cite a requirement as `[REQ-ID] - one-line meaning`; quote the
  statement verbatim when interpretation is disputed.
- Every requirement has a `Verification` pointer. Prefer an automated
  test; when impossible, record the exact manual or visual procedure.

## Documents

[Map of canonical docs - one line each. A pointer must say what the file
answers, not just name it; an unexplained path gets ignored.]

| File | Answers |
|------|---------|
| `docs/requirements.md` | [What user-visible behavior must be true - one stable ID, statement, and verification per entry] |
| `docs/decisions.md` | [Why, and what was rejected] |
| `MEMORY.md` | [Verified lessons learned - read at session start] |
| `PROGRESS.md` | [What's in flight now] |

[Rules for the doc set, if any - e.g. "canonical docs are corrected in
place, no archaeology; history lives in git". Cut if it doesn't apply.]

## Autonomy

[So a long unattended stretch stays productive without decisions being
made quietly. Keep exactly three tiers.]

| Tier | Trigger | Action |
|------|---------|--------|
| Decide and note | Routine judgement - naming, layout, a pinned version, a fixture's shape | Do it. One line in the commit body |
| Queue | A genuine fork (different answers lead to materially different work), but work remains that it does not block | Append to [QUESTIONS.md / backlog], continue with everything else |
| Stop | Nothing meaningful remains unblocked, or the action is irreversible or outward-facing | Halt and report |

## Safety

[HAND-ADD ONLY: the setup skill never writes this section - a working
rule in Working rules covers the common case ("never restart X"). Add
by hand when a repo warrants the full shape. Cut the section entirely
when it doesn't exist yet.]

[The rules with real blast radius - a pilot's checklist: short, every
line earned by a real failure. For each: the detection command to run
first, the enumerated actions that count as dangerous, the safe
alternative, and who owns the action.]

**[Dangerous thing]** - run `[detection command]` before acting. [What
counts as the dangerous action, enumerated - every form of it, not just
the obvious one.] If [detection says you're on prod]: stop and ask the
user; don't [do it] yourself. Default for experiments: [the isolated /
throwaway path], never prod.

## Maintenance

- Admission test for any new line: "would removing this cause a mistake?"
  If not, don't add it. Content derivable from code, enforced by a
  linter, or standard convention never belongs here.
- Add rules when a mistake repeats, not up front; prune as readily as
  added. A rule that describes code that has since changed is worse than
  no rule.
- Update this file at the correct scope when a change introduces a
  convention, gotcha, or trap future agents should know. A trap discovered
  in `<subdir>/` belongs in `<subdir>/AGENTS.md` if one exists, not here.
- [If the repo has MEMORY.md]: verified non-obvious learnings go there,
  not here - MEMORY.md carries the evidence (what broke, the fix), this
  file states the rule. When an entry's evidence stabilizes into a
  rule, promote it here and drop the entry.
