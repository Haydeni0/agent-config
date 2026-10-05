---
name: test-add
layer: worker
description: Use when user asks what tests are missing, what coverage is lacking, or which regressions are under-tested on the current branch/PR.
---

# Test Add

Find missing tests for current branch/PR changes and propose numbered test additions. Review-only: do not edit files in this skill.

Use shared workflow from `../test-pr-core/reference.md`, then apply this gap-specific rubric.

## Scope

- Decision scope: changed production code in `base...HEAD`.
- Test recommendations must map to this diff only.
- Context reads allowed: existing tests, fixtures, helper patterns, touched implementation.

## Gap Detection Rubric

For each changed symbol/path, evaluate coverage intent:

1. **Happy path**
   - core expected behavior validated?

2. **Boundary/path variation**
   - min/max/empty/null/alternate branch behavior tested?

3. **Failure contracts**
   - invalid inputs, exceptions, error messages, fallback behavior tested?

4. **Integration contract**
   - key external interactions verified (calls, side effects, serialization)?

5. **Regression risk**
   - changed bug-prone branches (conditionals, precedence, parsing, state transitions) guarded by tests?

## Prioritization

- `Critical`: high regression risk or core behavior untested
- `Major`: important branch/error/boundary path missing
- `Minor`: useful completeness coverage with lower immediate risk

## Output Addendum

In addition to shared format, include:

```markdown
## Missing Tests (Prioritized)
### Critical
1. `tests/path/test_file.py::test_name`: scenario, risk, expected assertion contract

### Major
1. ...

### Minor
1. ...

## Proposed Additions
1. file: `...`
   1. `test_...`
   2. `test_...`
```

Each missing-test finding must include:
- changed code location
- missing scenario
- risk if untested
- exact test placement recommendation

## Selection Gate

Ask user to pick numbered recommendations:

`Pick tests to add by number (for example: 1,3,4).`

