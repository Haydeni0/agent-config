---
name: test-trim
layer: worker
description: Use when user asks to clean up tests, remove redundant tests, dedupe tests, reduce test overlap, or simplify a test suite before PR.
deps: [test-pr-core]
---

# Test Trim

Review redundant tests in current branch/PR while preserving high-signal behavior coverage. Review-only: do not edit files in this skill.

Use shared workflow from `../test-pr-core/reference.md`, then apply this trim-specific rubric.

## Scope

- Primary target: changed test files only (`tests/**` in `base...HEAD`).
- Context reads allowed: related implementation files and nearby tests.
- Findings must remain scoped to changed tests.

## Trim Rubric (Aggressive)

1. **Duplicate behavior tests**
   - same setup, same behavior intent, same assertion contract
   - action: merge/delete; keep strongest version

2. **Near-duplicate test bodies**
   - differs only by input values
   - action: parametrize

3. **Repeated setup/mocking blocks**
   - copied fixture-like blocks across tests
   - action: helper fixture/extractor

4. **Low-signal tests**
   - assignment echo tests, type/existence-only checks, exit-code-only checks
   - action: remove or strengthen with behavior assertions

5. **Over-coupled implementation-detail assertions**
   - too many brittle assertions tied to internals
   - action: keep stable contract assertions only

## Keep Signals

Do not trim these without clear replacement:
- failure contracts (`raises`, specific errors)
- boundary/edge behavior
- precedence/conflict rules
- regression tests tied to known bugs

## Output Addendum

In addition to shared format, include:

```markdown
## Proposed Trims
1. delete: ...
2. merge: ...
3. parametrize: ...
4. extract fixture/helper: ...
```

