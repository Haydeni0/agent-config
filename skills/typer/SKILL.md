---
name: typer
description: Use when writing or editing any Python script that accepts command-line arguments - including standalone scripts, demos, benchmarks, experiments, profiling harnesses, and throwaway one-offs. Triggers on argparse, optparse, sys.argv, or any argv parsing in a Python file.
---

# Typer for Python CLIs

Use `typer` for any Python script that parses argv. Never `argparse`, `optparse`, or raw `sys.argv`.

This applies to all scripts with argv parsing, including throwaway, demo and benchmark scripts. If the project lacks typer, `uv add typer`; for a standalone script, declare it in a PEP 723 `# /// script` block.

## Basic Pattern

```python
import typer

app = typer.Typer()

@app.command()
def main(
    name: str,
    count: int = 1,
    verbose: bool = False,
):
    for _ in range(count):
        typer.echo(f"Hello {name}")

if __name__ == "__main__":
    app()
```

## Quick Reference

| Need | Typer syntax |
|------|-------------|
| Required arg | `name: str` |
| Optional with default | `count: int = 1` |
| Flag | `verbose: bool = False` |
| Explicit option | `name: str = typer.Option(...)` |
| Explicit argument | `path: str = typer.Argument(...)` |
| Fixed string choices (no class) | `quad: Literal["a", "b", "c"] = "a"` |
| Enum choices | `mode: MyEnum = MyEnum.fast` |
| Path | `out: Path = typer.Option(Path("."))` |
| Multiple subcommands | `app.command()` on multiple functions |

Type options at the boundary - see the global rules, "Programming principles: Python" ("Don't pass around strings for things that have a richer type").

## Argument Help

Add `help=` to every `typer.Option` / `typer.Argument`, and use `...` to mark a required param:

```python
@app.command()
def main(
    input_file: Path = typer.Argument(..., help="Path to input CSV"),
    workers: int = typer.Option(4, help="Number of parallel workers"),
):
    ...
```

Keep help strings brief - one clause, no full stops.

## Rules

- Use type hints - they ARE the argument definitions
- Use `typer.echo()` instead of `print()` for CLI output
