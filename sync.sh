#!/usr/bin/env bash
# Compatibility setup entry. Routine local changes: agent-config sync.
set -euo pipefail
script_path=${BASH_SOURCE[0]}
while [ -L "$script_path" ]; do
  script_dir=$(cd "$(dirname "$script_path")" && pwd -P)
  script_path=$(readlink "$script_path")
  case "$script_path" in /*) ;; *) script_path="$script_dir/$script_path" ;; esac
done
source_repo=$(cd "$(dirname "$script_path")" && pwd -P)
exec uv run --directory "$source_repo/settings-sync" agent-config --source "$source_repo" bootstrap "$@"
