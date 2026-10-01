---
summary: "Agent long-term memory - agent-config lessons learned"
read_when:
  - Starting work in this repo
  - Hitting a gotcha that might recur
  - Changing sync targets, overlays, native homes, hook trust, or launchers
---

# MEMORY.md - agent-config

Long-term memory for AI agents working in this repo. Read at session start;
append to it when you discover or fix something non-obvious. Do not duplicate
`AGENTS.md` rules here; an entry expands on a rule with the evidence (what
broke, the fix, the commit), since that provenance is the value this file adds
over the rule alone.

Rules:
- One entry per learning, newest at top.
- Date + one-line summary as a `###` heading, then the detail.
- Only verified facts confirmed this session; no guesses.
- Reference the commit that fixed it, where one exists.
- Prune: merge or drop entries whose constraint no longer holds; when an
  entry's evidence stabilizes into a standing rule, promote it to `AGENTS.md`
  and drop the entry.

## Learnings
