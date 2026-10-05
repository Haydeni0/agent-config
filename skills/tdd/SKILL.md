---
name: tdd
layer: worker
description: Use when implementing any feature or bugfix, before writing implementation code, or when using test-driven development.
---

This builds upon the `tdd-core` skill (its forked local copy). Invoke the `tdd-core` skill now, if not already.

Additional context to the `tdd-core` skill:

## Scaffolding Tests (Python projects)

During TDD cycles, write tests to a `tdd_scaffolding/` subdirectory within your project's test directory (e.g. `tests/tdd_scaffolding/`).

```text
<your test directory>/
├── tdd_scaffolding/   ← TDD cycle tests (temporary)
│   └── test_*.py
└── test_*.py          ← behavioral keeper tests
```

Scaffolding tests are fine-grained - they may test intermediate behaviors or internal units that don't meet the public-API standard. That's intentional: they drive implementation, not document behavior.

**At implementation complete:**
1. Delete the `tdd_scaffolding/` directory entirely
2. Verify the project's test suite has behavioral coverage for the implemented feature (per `pytest-guidelines`)
3. Add any missing behavioral tests before marking done
