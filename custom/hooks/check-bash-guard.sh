#!/usr/bin/env bash
# Claude compatibility entry point for installs whose settings still name this
# script; sync registers hooks/command.mjs directly. Shared policy lives in
# hooks/core/. The payload reaches command.mjs unmodified so command.mjs
# validates it; exit 2 makes bootstrap and runtime failures blocking.
set -euo pipefail
trap 'echo "Command guard could not run" >&2; exit 2' ERR
repo_dir=$(cd -P "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
node "$repo_dir/hooks/command.mjs" claude || exit 2
