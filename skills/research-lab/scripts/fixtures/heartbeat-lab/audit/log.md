# Audit log

Events: `GATE` (a gate ran), `CATCH` (a gate found a real error), `CRITIC_ERR`, `RULING`, `BUDGET`, `CUT`, `RETRACT` (see templates/audit-log.md).

| Time | Event | Experiment / page | Outcome | Detail | Evidence |
|---|---|---|---|---|---|
| 2020-01-01 09:00 | GATE | E1 design review | PASS | brief pre-registered | audit/E1-design.md |
| 2020-01-01 10:20 | CATCH | E1 | fixed | rounding drift in the timing script | experiments/E1.md |
