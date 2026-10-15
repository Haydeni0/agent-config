# Audit log

<!-- One line per gate outcome or critic error (D25). Feeds QR "which gates pay" and the
critic error rate (D14). Disputes are settled by the owner against the data (F25). -->

| Date | Gate | Experiment / page | Outcome | Caught (or critic error) | Evidence |
|---|---|---|---|---|---|
| 2026-10-15 | design review | E18 | PASS-WITH-FIXES | selection on the eval set (mini-val = final eval runs) | audit/E18-predispatch.md W1 |
| 2026-10-15 | result audit | R7-2 | PASS-WITH-FIXES | absolute-size decoding is a corpus confound | audit/R7-2.md |
| 2026-10-15 | page check | R1 E17, R2 E6 | fixed pre-publish | 6 wording errors | author 081 reply |
| 2026-10-15 | critic error | R1/R6 audits | 3 wrong corrections | owner re-check against JSON | false-findings F25 |
