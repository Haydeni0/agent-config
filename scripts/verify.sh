#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
cd "$script_dir/.."
uv run --locked --directory settings-sync pytest -q
uv run --locked --directory opencode-resume pytest -q
# -n 8 only on the subprocess-bound suites, fixed at 8 per REQ-PROCESS-06
# (-n auto would grab every core on large machines)
uv run --locked --directory settings-sync pytest ../custom/hooks/test_bash_guard.py -q -n 8
uv run --locked --directory settings-sync pytest ../skills/mailbox -q -n 8
uv run --locked --directory settings-sync pytest ../evals/claim-verification -q
uv run --locked --directory settings-sync python ../scripts/check-skills.py
uv run --locked --directory settings-sync python ../scripts/check_skill_graph.py
uv run --locked --directory settings-sync python ../scripts/check-packages.py
node --test hooks/tests/*.test.mjs harnesses/opencode/plugins/bash-guard.test.mjs harnesses/opencode/plugins/config-guard.test.mjs
bash -n sync.sh scripts/bootstrap.sh scripts/verify.sh

npm ci --ignore-scripts --prefix harnesses/pi
node --test harnesses/pi/tests/*.test.mjs
