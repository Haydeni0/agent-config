---
name: worktree-venv
description: Use when creating or running Python, uv or pytest inside a git worktree (or any second checkout of a repo that already has a virtual environment) - reuse the repo's existing venv instead of syncing a fresh one per worktree. Also use when a worktree cleanup is slow deleting a .venv.
---

# worktree-venv

Fresh `.venv` per worktree is a hidden recurring tax: uv sync is fast (hardlink cache) but
the venv is multi-GB with 100k+ files, and deleting it over NFS is per-unlink RPC -
minutes to tens of minutes, repeated for every scratch worktree. Reuse the repo's
environment instead.

## Default: reuse the repo's venv, never sync a local one

1. Find an existing venv for the repo: the main checkout's `.venv`, or a sibling
   worktree's. Use it READ-ONLY.
2. Run its binaries directly with `cwd` = the worktree: `<venv>/bin/python`,
   `<venv>/bin/pytest`, `<venv>/bin/ruff`, ... If you need uv's wrapper, use
   `uv run --no-sync` (or `UV_NO_SYNC=1`) - plain `uv run` or `uv sync` in the worktree
   creates/mutates a local `.venv` and defeats the point.
3. Mandatory probe, once per repo+venv combination, before trusting the reuse: from the
   worktree, import a deep module of the repo's own package and print its file:

   ```bash
   <venv>/bin/python -c "import <top_pkg>.<deep_module> as m; print(m.__file__)"
   ```

   - Prints the WORKTREE's path -> imports resolve via cwd/pytest rootdir; reuse is safe.
   - Prints the venv owner's tree (editable install pinned to one checkout) -> reuse is
     UNSAFE for that repo; fall back to an isolated env (below).

## When an isolated venv is required

Only when the task changes the environment itself: installing, upgrading or downgrading
any package; editing `pyproject.toml`, `uv.lock` or constraints; or the probe failed.

- Put the isolated env OUTSIDE the worktree (scratch dir or `/tmp`), e.g.
  `UV_PROJECT_ENVIRONMENT=<scratch>/.venv uv sync`, so worktree removal never has to
  delete it.
- Never sync into a venv another session or the user may be using; that venv is
  read-only by courtesy, `--no-sync` only.

## Deletion hygiene

Never block a task's critical path on `rm -rf` of a `.venv` over NFS. Background it and
carry on (report it if the caller tracks cleanup). `git worktree remove` fails on the
untracked `.venv` ("Directory not empty") after deregistering - expect that pattern:
deregister first, then the backgrounded delete of the residue.
