---
name: reflect
description: Use when the user invokes /reflect or asks to turn a session's learnings, friction, or mistakes into durable improvements for next time - AGENTS.md, MEMORY.md, global rules, skills, hooks, permissions, or the backlog. Triggers - "reflect on this", "what should we learn from this", "retro this session", "so this doesn't happen next time". Not auto-triggered - never invoke unless the user asks. DRAFT - read README.md alongside.
---

# reflect

> **DRAFT.** Shape is provisional until field-tested. Read `README.md` in
> this directory first - open questions and field notes from past runs
> live there.

Turn a session's learnings into the smallest durable change at the
right layer - often no change. The main failure mode is bloat: one new
rule per session until instruction files stop being read. Most
learnings do not earn a rule.

## 1. Harvest

Sources: the conversation, plus anything the user names (a handoff doc,
a transcript, a pasted summary). Look for:

- user corrections, repeated instructions, "no, I meant..."
- retries, dead ends, wasted tool calls, wrong assumptions
- things the user had to explain that the agent could not discover
- workarounds and manual steps that will recur

Each candidate: what happened, with evidence (quote the user, name the
failed command or edit), and what it cost.

## 2. Diagnose

Root cause before destination. Grep the existing rules, skills, and
memory for the topic first - if something already covers it, the cause
is never "missing".

| Cause | Typical fix |
|---|---|
| Missing knowledge - agent could not have known | Add the fact at the narrowest covering layer |
| Rule exists, was ignored | Not a new rule: sharpen wording or placement, add a rationalization row, or enforce mechanically |
| Rule exists, is wrong or stale | Edit or delete it |
| Skill procedure gap or misfire | Edit that skill |
| Tool or environment gap | Hook, script, permission, or backlog |
| One-off, unlikely to recur | Drop |
| Code or product defect | Not reflect's job - backlog in the owning repo |

Repetition earns rules. If you cannot tell whether this happened
before, ask the user.

## 3. Route

Narrowest layer that covers every future case. One home, never two
copies.

| Learning applies to | Destination |
|---|---|
| Every repo and harness | `rules/global.md` in the agent-config source checkout |
| One workflow or procedure | That skill in the agent-config source checkout |
| Must always hold and is mechanically checkable | Hook or permission (agent-config `harnesses/` or the repo's own), not prose |
| One repo or subtree - command, fact, rule | Innermost applicable `AGENTS.md` |
| One repo - verified gotcha with evidence | That repo's `MEMORY.md` |
| This machine only | agent-config overlays or native local state |
| Needs design or is not ready | `.agents/backlog.md` of the owning repo, via the backlog skill |

Repo without `AGENTS.md` / `MEMORY.md`: offer repo-agent-setup instead
of scaffolding ad hoc.

Admission test on every proposed line: "would removing this cause a
mistake?" Preference order: delete or edit an existing line > enforce
mechanically > add a line > add a file or skill.

## 4. Propose

One message first: a table of candidates - evidence, cause,
destination, recommendation (apply / drop / backlog). Then one
question at a time per kept candidate, showing the exact text and
location with an explicit **Recommend:**. `yes` accepts; free text
overrides. Plain chat text, never modal tools.

## 5. Apply

- agent-config destinations: edit the source checkout, never generated
  native copies; then `agent-config sync` and `agent-config check`.
  Skill edits follow the writing-skills skill.
- Repo destinations: follow that repo's own `AGENTS.md` rules (its
  requirements contract, maintenance rules, memory format).
- Write in the target file's voice and rules - no dates or incident
  history in rules; dated evidence belongs in `MEMORY.md`.
- Stage with `git add`. Commit only under the global git gate.

## 6. Report

One line per candidate: applied (where), dropped (why), or backlogged
(ID). Then one question: "anything about /reflect itself feel off? I
can log a field note to its README." On yes, append per the README's
field-note template.
