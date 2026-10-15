#!/usr/bin/env bash
# Launch one lab member in its own herdr tab and hand it its connect prompt; prints the pane id.
# Usage: spawn-member.sh <member-name> <cwd> <prompt-file>
# The launcher comes from the PI profile's LAUNCHER line, never a harness default:
# `herdr agent start --kind claude` runs the native binary, ignoring the profile.
set -euo pipefail
name=$1 cwd=$2 prompt_file=$3
profile=${RESEARCH_LAB_PROFILE:-$HOME/.config/research-lab/pi-profile.md}
launcher=$(sed -n 's/^LAUNCHER: *//p' "$profile" | head -1)
[[ -n $launcher ]] || { echo "spawn-member: no 'LAUNCHER:' line in $profile" >&2; exit 1; }
[[ -r $prompt_file ]] || { echo "spawn-member: prompt file $prompt_file unreadable" >&2; exit 1; }

pane=$(herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$cwd" --label "$name" --no-focus \
  | jq -r '.result.root_pane.pane_id')
[[ $pane == *:p* ]] || { echo "spawn-member: tab create for $name failed" >&2; exit 1; }
herdr pane run "$pane" "$launcher" >/dev/null
# herdr only knows the pane as an agent once the harness has drawn its UI
for _ in $(seq 60); do herdr agent get "$pane" >/dev/null 2>&1 && break; sleep 2; done
# A cwd the harness has not seen opens its folder-trust dialog. Accept it only for a cwd under
# a root the PI listed in the profile (TRUSTED_ROOTS:) and only when the dialog names that
# cwd and shows the expected option; anything else stops for the PI.
cwd_real=$(realpath "$cwd")
trusted=no
for root in $(sed -n 's/^TRUSTED_ROOTS: *//p' "$profile" | head -1); do
  root_real=$(realpath -m "${root/#\~/$HOME}")
  [[ $cwd_real == "$root_real" || $cwd_real == "$root_real"/* ]] && trusted=yes
done
for _ in $(seq 15); do
  screen=$(herdr pane read "$pane")
  if grep -q "trust this folder" <<<"$screen"; then
    if [[ $trusted != yes ]] || ! grep -qF "$cwd_real" <<<"$screen" \
        || ! grep -q "Yes, I trust this folder" <<<"$screen"; then
      echo "spawn-member: $pane waits on a folder-trust dialog for $cwd_real, outside TRUSTED_ROOTS; ask the PI" >&2
      exit 2
    fi
    herdr pane send-keys "$pane" Down >/dev/null
    grep -q "❯ Yes, I trust this folder" <<<"$(herdr pane read "$pane")" \
      || { echo "spawn-member: trust dialog in $pane did not select 'Yes'; ask the PI" >&2; exit 2; }
    herdr pane send-keys "$pane" Enter >/dev/null
    break
  fi
  [[ $(herdr agent get "$pane" | jq -r '.result.agent.agent_status') == idle ]] && break
  sleep 2
done
herdr agent wait "$pane" --until idle --timeout 180000 >/dev/null
herdr agent prompt "$pane" "$(cat "$prompt_file")" >/dev/null
# a prompt typed while the UI is still settling can sit unsubmitted in the input box
sleep 5
[[ $(herdr agent get "$pane" | jq -r '.result.agent.agent_status') == working ]] \
  || herdr pane send-keys "$pane" Enter >/dev/null
herdr agent rename "$pane" "$name" >/dev/null
echo "$pane"
