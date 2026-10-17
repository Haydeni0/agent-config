---
name: knowledge
description: Use when a session is about to research, test, measure or decide something that may already be settled, when a verified claim is learned and worth keeping, or when the user says "what do we know about X", "add that to the knowledge store", "check the knowledge base", "sweep the knowledge store". Triggers - starting any research or spike, closing a lab or verified investigation, contradicting or superseding a known claim, periodic re-validation.
---

# Knowledge

The private knowledge store (`~/gitrepos/knowledge` by default,
`KNOWLEDGE_STORE` to override) is searched first, before the internet, the
filesystem or any tool: if the store settles the question, nothing else
gets read. Its `AGENTS.md` is the contract and owns every rule; this skill
never restates it - load it before any add or supersede:

```
cat ~/gitrepos/knowledge/AGENTS.md
```

## search (before any research)

```
uv run --script <skill dir>/knowledge.py search <word> [<word> ...]
```

All words must match (AND). Hits print domain, claim and parts. A search
that misses an entry known to exist gets logged to `sweep-log.md` with
query and reason (the store's rule 7: rg is the index; an embedding
cache is earned only by logged recall failures).

## add (a verified claim)

Propose the entry in the store's fixed shape on stdin, domain file name as
the only argument:

```
uv run --script <skill dir>/knowledge.py add <domain>.md <<'EOF'
- claim: <one sentence, scope baked in>
  kind: fact | finding | pattern | ruling | method
  project: <project or global>   (optional)
  source: <durable pointer, never a gitignored scratch path>
  how-verified: <the mechanism that actually ran>
  level: replicated | audited | observed | cited | superseded
  date: <from date>
  scope: <validity boundary + measured noise band, verbatim from source>
  links: [[<entry or hub>]] <why>   (optional)
EOF
```

The tool enforces the mechanical gates: required parts, kind/level
vocabulary, scratch-pointer refusal, future-date refusal, and the
admission gate (every path named in `source`/`how-verified` must exist -
commit SHAs and URLs pass). Duplicate claims return `NOOP` naming the
existing entry; a richer restatement of an existing claim is an in-place
`UPDATE` by a session that has read the contract's rules. A contradicted
claim is superseded in place by a session, never deleted.

The commit in the store is the session's to make through the normal git
gate of the environment the session runs in.

## sweep (re-validation)

```
uv run --script <skill dir>/knowledge.py sweep [--env-max-age-days N]
```

Flags only, never edits: entries whose `how-verified` names paths that no
longer exist, and environment facts (`kind: fact`) older than the cadence
(default 365 days). Flags land in `sweep-log.md` for the PI to rule on.
