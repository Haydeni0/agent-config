#!/usr/bin/env bash
# Claude compatibility entry point. Shared policy lives in hooks/core/.
# Exit 2 makes bootstrap and runtime failures blocking hook failures.
set -euo pipefail
trap 'echo "Command guard could not run" >&2; exit 2' ERR
repo_dir=$(cd -P "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
jq '.hook_event_name //= "PreToolUse" | .tool_name //= "Bash" | .tool_input.command //= ""' |
  node "$repo_dir/hooks/command.mjs" claude
