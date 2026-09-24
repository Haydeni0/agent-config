#!/usr/bin/env bash
# Explicit external installs. Local rendering belongs to agent-config sync.
set -uo pipefail
source_repo=${1:?source checkout required}
harness=${2:?harness required}
EVO_VERSION=0.8.0
NO_MISTAKES_VERSION=v1.79.0
# Release artifact installation follows docs/install.sh at this upstream revision.
NO_MISTAKES_INSTALLER_REVISION=c1d8a2cd36050061b8f63bb6e1b040a61d759cd8
pi_home=${AGENT_CONFIG_PI_HOME:-$HOME/.pi/agent}
nomistakes_home=${AGENT_CONFIG_NOMISTAKES_HOME:-$HOME/.no-mistakes}
exit_code=0
unset PI_CODING_AGENT_DIR
fail() { echo "bootstrap: $*" >&2; exit_code=1; }
require() { command -v "$1" >/dev/null 2>&1 || { fail "missing prerequisite: $1"; return 1; }; }

pi_package_matches() {
  case "$1" in
    npm:*)
      local package=${1#npm:}
      local name=${package%@*} version=${package##*@}
      [ "$name" != "$package" ] && [ -f "$pi_home/npm/node_modules/$name/package.json" ] &&
        [ "$(jq -r .version "$pi_home/npm/node_modules/$name/package.json")" = "$version" ]
      ;;
    git:*)
      local package=${1#git:}
      local repository=${package%@*} revision=${package##*@}
      [ "$repository" != "$package" ] &&
        [ "$(git -C "$pi_home/git/$repository" rev-parse HEAD 2>/dev/null)" = "$revision" ]
      ;;
    *) return 1 ;;
  esac
}

ensure_evo() {
  require uv || return 1
  if ! uv tool list | awk -v expected="v$EVO_VERSION" '$1 == "evo-hq-cli" && $2 == expected { found=1 } END { exit !found }'; then
    uv tool install --force "evo-hq-cli==$EVO_VERSION" || { fail "evo CLI install failed"; return 1; }
  fi
  evo_executable="$(uv tool dir)/evo-hq-cli/bin/evo"
}

case "$harness" in
  pi)
    require pi && require jq && require git || exit 1
    template="$source_repo/harnesses/pi/settings.json"
    packages=$(jq -er '.packages // [] | .[]' "$template")
    parse_status=$?
    if [ "$parse_status" -ne 0 ] && [ "$parse_status" -ne 4 ]; then
      fail "invalid packages declaration: $template"
      exit 1
    fi
    while IFS= read -r spec; do
      [ -n "$spec" ] || continue
      if pi_package_matches "$spec"; then
        echo "bootstrap: matching $spec"
      elif ! PI_CODING_AGENT_DIR="$pi_home" pi install "$spec"; then
        fail "pi install $spec failed"
      elif ! pi_package_matches "$spec"; then
        fail "pi install $spec failed to produce the pinned version"
      fi
    done <<< "$packages"
    extension="$source_repo/harnesses/pi/extensions/web-access"
    if [ -f "$extension/package.json" ]; then
      require npm && (cd "$extension" && npm ci) || fail "web-access npm ci failed"
    fi
    ;;
  claude|opencode)
    require "$harness" && ensure_evo || exit 1
    if [ "$harness" = claude ]; then
      if [ -f "$HOME/.claude/plugins/cache/evo-hq-evo/evo/$EVO_VERSION/.claude-plugin/plugin.json" ]; then
        echo "bootstrap: matching Claude Evo $EVO_VERSION"
      else
        "$evo_executable" install claude-code --version "$EVO_VERSION" || fail "Claude Evo install failed"
        [ -f "$HOME/.claude/plugins/cache/evo-hq-evo/evo/$EVO_VERSION/.claude-plugin/plugin.json" ] || fail "Claude Evo version verification failed"
      fi
    else
      tool_root=$(uv tool dir) || exit 1
      bundles=("$tool_root"/evo-hq-cli/lib/python*/site-packages/evo/opencode_plugin/evo.bundle.js)
      [ "${#bundles[@]}" -eq 1 ] && [ -f "${bundles[0]}" ] || { fail "pinned Evo bundle unavailable"; exit 1; }
      target_dir="${OPENCODE_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/opencode}/plugins"
      mkdir -p "$target_dir" || exit 1
      if ! cmp -s "${bundles[0]}" "$target_dir/evo.js"; then
        stage=$(mktemp "$target_dir/.evo.XXXXXX") || exit 1
        if cp "${bundles[0]}" "$stage" && chmod 644 "$stage" && mv "$stage" "$target_dir/evo.js"; then
          echo "bootstrap: installed pinned Evo bundle $EVO_VERSION"
        else
          rm -f "$stage"
          fail "Opencode Evo install failed"
        fi
      fi
    fi
    ;;
  no-mistakes)
    if command -v no-mistakes >/dev/null 2>&1; then
      echo "bootstrap: no-mistakes already installed; native updater owns upgrades"
    else
      require curl && require tar || exit 1
      platform=$(uname -s | tr '[:upper:]' '[:lower:]')
      architecture=$(uname -m)
      case "$platform" in linux|darwin) ;; *) fail "unsupported platform: $platform"; exit 1 ;; esac
      case "$architecture" in x86_64|amd64) architecture=amd64 ;; arm64|aarch64) architecture=arm64 ;; *) fail "unsupported architecture: $architecture"; exit 1 ;; esac
      stage=$(mktemp -d) || exit 1
      trap 'rm -rf "$stage"' EXIT
      artifact="no-mistakes-$NO_MISTAKES_VERSION-$platform-$architecture.tar.gz"
      curl -fsSL "https://github.com/kunchenguid/no-mistakes/releases/download/$NO_MISTAKES_VERSION/$artifact" -o "$stage/release.tar.gz" &&
        tar xzf "$stage/release.tar.gz" -C "$stage" &&
        mkdir -p "$nomistakes_home/bin" "$HOME/.local/bin" &&
        install -m 755 "$stage/no-mistakes" "$nomistakes_home/bin/no-mistakes" &&
        ln -sfn "$nomistakes_home/bin/no-mistakes" "$HOME/.local/bin/no-mistakes" &&
        "$nomistakes_home/bin/no-mistakes" daemon restart || fail "no-mistakes install failed"
    fi
    ;;
  codex|goose|agy) require "$harness" || exit 1; echo "bootstrap: $harness has no declared external installs" ;;
  *) fail "unknown harness: $harness" ;;
esac
exit "$exit_code"
