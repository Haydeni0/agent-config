#!/usr/bin/env bash

input=$(cat)

# --- Parse JSON fields ---
model_name=$(echo "$input" | jq -r '.model.display_name // .model // "?"')
cwd=$(echo "$input" | jq -r '.cwd // .workspace.current_dir // "~"')
cost_usd=$(echo "$input" | jq -r '.cost.total_cost_usd // 0')
cur_in=$(echo "$input" | jq -r '.context_window.current_usage.input_tokens // 0')
cache_create=$(echo "$input" | jq -r '.context_window.current_usage.cache_creation_input_tokens // 0')
cache_read=$(echo "$input" | jq -r '.context_window.current_usage.cache_read_input_tokens // 0')
context_size=$(echo "$input" | jq -r '.context_window.context_window_size // 200000')

# --- Colors (ANSI 256) ---
cyn=$'\033[36m'
mag=$'\033[35m'
slt=$'\033[38;2;94;115;168m'   # #5e73a8 slate blue
cfb=$'\033[38;2;100;149;237m'  # cornflower blue #6495ed
blu=$'\033[34m'
grn=$'\033[32m'
ylw=$'\033[33m'
red=$'\033[31m'
dim=$'\033[90m'   # brightBlack
rst=$'\033[0m'
sep=" | "

# ============================================================
# Widget: backend  (green=official Anthropic, yellow=custom gateway)
# ============================================================
base_url="${ANTHROPIC_BASE_URL:-}"
if [ -z "$base_url" ] || [[ "$base_url" =~ ^https://api\.anthropic\.com ]]; then
    backend_w="${grn}Backend: api.anthropic.com${rst}"
else
    # strip scheme, keep host[:port]
    backend_host="${base_url#*://}"
    backend_w="${ylw}Backend: ${backend_host}${rst}"
fi

# ============================================================
# Widget: model  (cyan)
# ============================================================
model_w="${cyn}Model: ${model_name}${rst}"

# ============================================================
# Widget: context-bar  (brightBlack, 16-char bar / progress-short)
# ============================================================
used_tokens=$((cur_in + cache_create + cache_read))
[ "$context_size" -le 0 ] 2>/dev/null && context_size=200000

used_pct_raw=$(echo "scale=4; $used_tokens * 100 / $context_size" | bc -l 2>/dev/null || echo "0")
used_pct=$(printf "%.0f" "$used_pct_raw" 2>/dev/null || echo "0")
filled=$(printf "%.0f" "$(echo "$used_pct * 16 / 100" | bc -l 2>/dev/null || echo 0)")
[ "$filled" -gt 16 ] 2>/dev/null && filled=16

bar=""
for ((i=0; i<16; i++)); do
    if [ "$i" -lt "$filled" ] 2>/dev/null; then
        if   [ "$used_pct" -lt 50 ] 2>/dev/null; then bar+="${grn}█"
        elif [ "$used_pct" -lt 75 ] 2>/dev/null; then bar+="${ylw}█"
        else bar+="${red}█"; fi
    else
        bar+="${dim}░"
    fi
done
bar+="${rst}"

usedK=$((used_tokens / 1000))
totalK=$((context_size / 1000))
ctx_w="${dim}Context: ${bar}${dim} ${usedK}k/${totalK}k (${used_pct}%)${rst}"

# ============================================================
# Widget: session-cost  (magenta)
# ============================================================
cost_fmt=$(printf '$%.2f' "$cost_usd")
cost_w="${slt}Cost: ${cost_fmt}${rst}"

# ============================================================
# Widget: thinking-effort  (magenta)
# ============================================================
effort=$(echo "$input" | jq -r '.effort.level // "medium"')
thinking_w="${slt}Thinking: ${effort}${rst}"

# ============================================================
# Widget: git-auth-gates  (green=authorised, red=locked)
# Shows COMMIT_AUTHORISED / PUSH_AUTHORISED env state.
# NOTE: statusline runs as a child of the Claude Code process, so
# it inherits the session env - set/unset in the launching shell.
# ============================================================
gate_w="${red}Gates: C✗ P✗${rst}"
[ "${COMMIT_AUTHORISED:-}" = "1" ] && gate_w="${grn}Gates: C✓${rst}${red} P✗${rst}"
[ "${PUSH_AUTHORISED:-}" = "1" ] && gate_w="${grn}Gates: P✓${rst}${red} C✗${rst}"
if [ "${COMMIT_AUTHORISED:-}" = "1" ] && [ "${PUSH_AUTHORISED:-}" = "1" ]; then
    gate_w="${grn}Gates: C✓ P✓${rst}"
fi

# ============================================================
# Widget: git-branch  (magenta)
# ============================================================
cd "$cwd" 2>/dev/null || cd ~
git_branch_w=""
if git rev-parse --git-dir >/dev/null 2>&1; then
    branch=$(git branch --show-current 2>/dev/null)
    if [ -n "$branch" ]; then
        git_branch_w="${slt}⎇ ${branch}${rst}"
    fi
fi
[ -z "$git_branch_w" ] && git_branch_w="${slt}⎇ no git${rst}"

# ============================================================
# Widget: current-working-dir  (blue)
# ============================================================
display_cwd="${cwd/#$HOME/~}"
cwd_w="${cfb}${display_cwd}${rst}"

# ============================================================
# Output
# ============================================================

# Line 1: model | ctx | cost | thinking
line1="${model_w}${sep}${ctx_w}${sep}${cost_w}${sep}${thinking_w}"

# Line 2: git-branch | cwd | gates | backend
line2="${git_branch_w}${sep}${cwd_w}${sep}${gate_w}${sep}${backend_w}"

printf '%s\n' "$line1"
printf '%s'   "$line2"
