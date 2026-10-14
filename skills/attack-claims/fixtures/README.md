# attack-claims fixtures

Claim set for behavioral and E2E runs of the attack-claims skill. Generate the
data fixtures into a scratch dir first: `uv run skills/attack-claims/fixtures/make_fixtures.py <dir>`.
Ground truth is what the fixture planted or what was verified when it was
picked; the expected outcome is what a correct run reports.

| ID | Claim (verbatim) | Subject | Mode | Setup overrides | Ground truth | Expected |
|---|---|---|---|---|---|---|
| F1 | In f1.csv, A has a direct association with B: the A-B correlation persists after controlling for Z. | `<dir>/f1.csv` | attacker-gathered | - | A and B correlate only through Z (partial corr ~0) | `contradicted`, computational evidence, audit re-ran the script |
| F2 | In f2.csv, A is associated with B, and the association persists after controlling for Z. | `<dir>/f2.csv` | attacker-gathered | - | Direct A->B effect, Z independent | `passed` after all 3 waves |
| F3 | The paper 'Interpreting neural operators: how nonlinear waves propagate in non-reciprocal solids' (arXiv 2404.12918) has no public code release. | arXiv 2404.12918 | attacker-gathered | - | https://github.com/jcolen/microfluidics_neural_operators (author-owned, first author Colen): paper text has no github/gitlab/code-is-available link and the arXiv abs page has no code link; repo README names the manuscript and the arXiv id | `contradicted` via existence (repo URL + quote) |
| F4 | On the SPOT benchmark (arXiv 2505.11855), the best-performing model, o3, reaches 21.1% recall and 6.1% precision. | arXiv 2505.11855 | attacker-gathered | - | Figures as quoted in the critic spike's lit-debate stream | `passed`; `contradicted`/`not_entailed` if the paper's figures differ or are absent (then the stream misquoted) |
| F5 | `scripts/check-skills.py` passes when a `layer: worker` skill's body names an orchestrator-layer skill such as `research-spike`. | this repo at `abddc709cc88` | attacker-gathered | - | check-skills fails with "worker names orchestrator skill" | `contradicted`; user's tree untouched; any worktree under `<workspace>/worktrees/`, removed at teardown |
| F6 | The function f(x) = x**4 - 3*x**2 is convex on the real line. | math | attacker-gathered | - | f(0)=0 > (f(-1)+f(1))/2 = -2 | `contradicted` via numeric counterexample |
| F7 | `f7/answer.md` (3 claims) | `f7/spans.json` | verify-only | - | true / opposite of README line 9 / not in README | `passed` / `not_entailed` or `contradicted` / `not_entailed` |
| F8 | In the CSV served at http://127.0.0.1:8765/big.csv, the row with id 190000 has value 4242. | http://127.0.0.1:8765/big.csv, served from memory by `uv run skills/attack-claims/fixtures/serve_f8.py` (no on-disk artifact; target value drawn at launch and echoed to the server's stderr) | attacker-gathered | per-download cap 1 MB | row 190000 value = serve-time SystemRandom draw (echoed to the server's stderr at launch; recorded in the run deviation log only, never committed); CSV ~2.2 MB in memory, row past the first 1 MB | `unverifiable (searched)`, angle blocked by storage, nothing over 1 MB in the workspace |
