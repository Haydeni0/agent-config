#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
cd "$script_dir/.."
uv run --locked --directory settings-sync pytest -q
uv run --locked --directory opencode-resume pytest -q
uv run --locked --directory settings-sync pytest ../custom/hooks/test_bash_guard.py -q
node --test harnesses/opencode/plugins/bash-guard.test.mjs harnesses/opencode/plugins/config-guard.test.mjs
bash -n sync.sh scripts/bootstrap.sh scripts/verify.sh

npm ci --ignore-scripts --prefix harnesses/pi
node --test harnesses/pi/tests/config-guard.test.mjs
