#!/usr/bin/env bash
# caveman SessionStart activation hook
# Bash port of vendor/plugins/caveman/hooks/caveman-activate.js - no node required.
# Sync manually if upstream JS changes after a submodule update.

repo_root=$(cd -P "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)
SKILL_FILE="$repo_root/vendor/plugins/caveman/skills/caveman/SKILL.md"

if [ -f "$SKILL_FILE" ]; then
    # Strip YAML frontmatter (between first and second ---)
    awk 'BEGIN{f=0;c=0} /^---/{c++;if(c==2){f=1;next}} f{print}' "$SKILL_FILE"
else
    echo "caveman skill missing at $SKILL_FILE; run git submodule update --init --recursive in the agent-config checkout" >&2
fi
