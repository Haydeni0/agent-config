# Audit log

<!-- One line per event (D25, D35). Event is one of the fixed vocabulary below, so D28
measures and D32 budget-vs-actual are grep-able. "Detail" carries the failure text (what the
check or critic saw), not just "caught": it is the trace the end-of-lab template pass reads. The Time cell is the output of
`date +'%Y-%m-%d %H:%M'` run in the same command that writes the row, never an estimate; write
rows with a single-quoted heredoc so the shell does not mangle them. -->

Events: `GATE` (a gate ran: design review, result audit, attack-claims, page audit, checker),
`CATCH` (a gate found a real error), `CRITIC_ERR` (a critic finding was wrong, settled against
the data), `RULING` (overseer settled a finding after the revision cap), `BUDGET` (an
experiment closed: budget vs actual), `CUT` (scope cut, D32), `RETRACT` (claim retracted,
D24).

| Time | Event | Experiment / page | Outcome | Detail | Evidence |
|---|---|---|---|---|---|
| 2026-10-15 14:10 | CATCH | E18 design review | PASS-WITH-FIXES | mini-val reused the final eval ids: selection on the eval set | audit/E18-predispatch.md W1 |
| 2026-10-15 15:20 | BUDGET | E18 | 40 h projected vs 6 h budget | data_wait 157 s/step under CPU contention | finetune.log |
| 2026-10-15 16:20 | CRITIC_ERR | R1/R6 audits | 3 wrong corrections | critic recomputed from a summary, not the JSON | false-findings F25 |
