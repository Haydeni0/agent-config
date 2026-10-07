---
name: pytest-guidelines
description: Use when writing or reviewing Python tests, when tests import unittest.mock, when keeper tests target private methods or implementation details, or when fixture params or definitions lack type annotations.
deps: [uv, tdd]
---

# Pytest Guidelines

## Overview

Keeper tests document **public behavior** only. During TDD, temporary tests live in `tests/tdd_scaffolding/` and are deleted when done.

## Quick Reference

| Do | Don't |
|---|---|
| `uv run pytest` | bare `pytest`, `python -m pytest`, `.venv/bin/pytest` |
| `mocker.patch(...)` (`pytest-mock`) | `unittest.mock` |
| Patch where the name is **used**, not where it's defined | patch at definition site |
| Test public inputs/outputs and side effects | test `_private` methods in keeper tests |
| `@pytest.mark.parametrize` for input variants | loops inside test bodies |
| `with pytest.raises(...)` for errors | manual try/except in tests |
| Type every fixture param and `@pytest.fixture` return | untyped fixtures or `Any` on fixture params |

Discovery: files `test_*.py`, functions `test_*()`, classes `Test*`. Shared fixtures in `tests/conftest.py`.

## Running

**REQUIRED:** See `uv` skill. Always `uv run pytest [args...]`.

## Mocking

Never import or use `unittest.mock`. Use the `pytest-mock` `mocker` fixture only - mocks auto-stop after each test.

```python
mock_get = mocker.patch("my_package.api_client.requests.get", ...)
mock_get.assert_called_once_with(...)
```

If a project lacks `pytest-mock`, add it (`uv add pytest-mock`) - do not fall back to `unittest.mock`.

## Keeper Tests

Applies to tests in `tests/` outside `tdd_scaffolding/`.

Test **observable behavior** through public APIs. Never write keeper tests for names starting with `_`.

If refactoring internals forces keeper test changes, the test was too coupled - rewrite at a higher level.

### Naming and Content

- Short names when unambiguous: if the only test for `foo` is `test_foo`, don't write `test_foo_does_x_when_called_with_y`. Add a distinguishing suffix only when multiple tests cover one function.
- Neutral data names, not usage names: `array1`, `array2` not `volume.pressure`, `volume.velocity` when the code under test takes arbitrary arrays - usage names imply a domain contract the test doesn't exercise.
- Concrete inputs, literal expected outputs. `assert calc(100) == 108.875`, not `assert calc(x) == x * 1.08875` - a recomputed expectation re-implements the logic and fails with it.
- Don't restate in test comments what the tested object's public docstring already says, and don't narrate implementation details - the reader has the code.

### Rationalizations

| Excuse | Reality |
|---|---|
| "The bug is in the private helper" | Exercise it through the public API that calls it |
| "Easier to unit-test in isolation" | Use `tests/tdd_scaffolding/` during TDD, then delete |
| "I'll mock with unittest.mock quickly" | Use `mocker`; install `pytest-mock` if missing |
| "This helper is stable enough to test directly" | Stability doesn't make it public API |
| "Scaffolding is useful documentation - keep it" | Convert edge cases to keeper tests; delete `tdd_scaffolding/` |

### Red Flags - STOP

- Keeper test imports or calls `_something`
- `from unittest.mock import patch` or `import unittest.mock`
- Granular TDD test left in `tests/` after implementation complete
- Bare `pytest` in commands

## Typing

Review aid for keeper tests - not full typing enforcement. Scaffolding exempt.

Type **all fixtures** in keeper tests:

- **`@pytest.fixture` definitions:** always `-> ReturnType`
- **Test params:** annotate every injected fixture, including built-ins and plugin fixtures
- **Chained fixtures:** annotate fixture params that depend on other fixtures
- Skip `-> None` on test functions

Plugin fixtures: use types from plugin stubs or docs - never `Any` for convenience.

### Built-in fixture types

| Fixture | Type |
|---|---|
| `tmp_path` | `pathlib.Path` |
| `tmp_path_factory` | `pytest.TempPathFactory` |
| `monkeypatch` | `pytest.MonkeyPatch` |
| `capsys` / `capfd` | `pytest.CaptureFixture[str]` |
| `mocker` | `pytest_mock.MockerFixture` |
| `request` | `pytest.FixtureRequest` |

```python
@pytest.fixture
def calculator() -> OrderCalculator:
    return OrderCalculator()

def test_total(mocker: MockerFixture, calculator: OrderCalculator):
    ...
```

## TDD Scaffolding

**REQUIRED BACKGROUND:** Use `tdd` skill. Scaffolding tests may target internals; they are temporary and deleted before done. Convert behavior to keeper tests per this skill.

## Common Mistakes

- Patching `my_package.utils.requests` when code imports `requests` inside `api_client` - patch `my_package.api_client.requests`
- Leaving `tdd_scaffolding/` after TDD completes
- Testing return value structure field-by-field when one behavioral assertion suffices
- `@pytest.fixture` duplicated across files instead of shared `conftest.py`
- Custom fixture without return type in keeper tests
- Untyped fixture param on keeper test (`tmp_path` with no annotation)
- `Any` on a fixture param when a concrete type exists
- Expected output recomputed with the same expression the code under test uses (tautology)
- Overly long test name for a function with a single test

## Example

Public API test with typed fixture and mock:

```python
import pytest
from pytest_mock import MockerFixture


@pytest.fixture
def calculator() -> OrderCalculator:
    return OrderCalculator()


def test_order_total_includes_ny_tax(mocker: MockerFixture, calculator: OrderCalculator):
    mocker.patch("my_package.tax.lookup_rate", return_value=0.08875)
    total = calculator.get_order_total(subtotal=100, state="NY")
    assert total == pytest.approx(108.875)
```
