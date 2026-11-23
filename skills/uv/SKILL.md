---
name: uv
description: Use when running Python, managing Python packages, setting up environments, or running pytest.
---

# Using uv

All Python package management uses `uv`. Never use `pip`, `pip3`, `python -m pip`, `conda`, or `poetry`.

## Running

Use `uv run` - never activate the venv directly:

```bash
uv run python script.py
uv run pytest [args...]
uv run <tool>
```

## Common Commands

| Task | Command |
|------|---------|
| Check if package is installed | `uv pip show <pkg>` |
| Install package | `uv pip install <pkg>` |
| Install from requirements | `uv pip install -r requirements.txt` |
| Install project deps | `uv pip install -e .` |
| Add to pyproject | `uv add <pkg>` |
| Run script | `uv run python script.py` |
| Run tool (no install) | `uvx <tool>` |

## Rules

- NEVER activate the venv with `source` - use `uv run`
- NEVER patch the venv - do not edit, create, or delete files under `.venv/`. Manage packages via `uv add` / `uv pip install` only
- Package source code lives at `./.venv/lib/<python_version>/site-packages/`
