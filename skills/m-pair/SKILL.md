---
name: m-pair
description: Use when the user wants to start a marimo notebook or pair on an active marimo session - run Python in the same kernel, inspect live notebook state, or commit durable notebook changes.
deps: [marimo-pair]
---

# m-pair (wrapper)

Thin wrapper around the `marimo-pair` skill (a git submodule we do not edit). The
real content lives under `marimo-pair`; this wrapper keeps a local name (`/m-pair`)
plus a gotcha we do not want to push upstream. See `README.md` for why.

**REQUIRED SUB-SKILL:** Use `marimo-pair` for the full guide. Load it before acting.

## Auth gotcha

`execute-code.sh` reads the token from `MARIMO_TOKEN` env or `--token`, NOT
from a `?access_token=` query param in `--url`. If a notebook URL carries
`?access_token=...`, extract it and pass via `MARIMO_TOKEN` with a clean
`--url` (path only) - otherwise the `/api/sessions` request mangles the query
param into the path and returns "No active sessions" even when one exists.

## General marimo gotchas

See [MEMORY.md](MEMORY.md) for marimo quirks to remember.
