# Critic-bench fixtures

Copies from research-lab-pilot's critic bench (`tests/critic-bench/`, exp commit
d2f829a08 of the T1 GNO-kernels lab): 10 single-fault variants of the audited E1
entry plus the control (v05/v10 are byte-identical to v01 and not copied), the
control manifest, the fault-a manifest (its `c-b-share-bf16` quote was mutated
alongside the prose), and the result JSON the checks read. Fault letters a-i and
expected outcomes: `../test_lab_checker.py` and the pilot's
`tests/critic-bench/{key.md,results.md}`.

Only change from the bench copies: each manifest's `DATA` constant points at
`e1_stage_timing.json` in this directory instead of the T1 lab worktree.
