#!/usr/bin/env bash
# PreToolUse hook: hard-deny destructive bash commands.
#
# Reads the Claude Code hook JSON from stdin; emits a deny decision JSON to
# stdout when the command would perform a blocked action, otherwise emits
# nothing (allow).
#
# Bypass-resistance: no `if` matcher is used upstream (matchers fail open on
# $()/backticks). This script runs on every Bash command and uses a cheap
# grep pre-check, then tokenizes - flattening shell metachars
# (" ' ` $ ( ) ; & | \) to spaces - so wrapped forms (bash -c "...", $(...),
# a && b, a ; b, \rm) still match. Layered with permissions.deny (unbypassable
# floor); this hook catches the wrapper/compound/flag-reorder cases the
# deny globs miss.
#
# Scope (per user choice):
#   S3:       hard deny deletes only (rm, rb, sync --delete, s3api delete-*).
#             Uploads and read ops stay allowed.
#   /mnt/data: deny ALL deletes under /mnt/data (rm, rmdir, shred, unlink,
#             trash, find -delete, find -exec/-ok rm). Reads/writes allowed.
#   /mnt:     deny deletes on /mnt (parent of /mnt/data).
#   root:     deny deletes on / or /* (any flag arrangement).
#   sudo:     deny any use of sudo.
#   dd:       deny any use of dd.
#   mkfs:     deny any use of mkfs.
#   chmod 777: deny chmod with a 777-granting octal mode (777, 0777, 1777).
#   git push: deny git push --force / -f (incl. short-flag clusters like -fq,
#             -qf) and +refspec (+main:main). Plain push and
#             --force-with-lease stay allowed.
#   gh api:   deny write methods (-X/--method DELETE/POST/PATCH/PUT, incl.
#             attached forms -XDELETE), --input, and request fields
#             -f/-F/--raw-field/--field (gh auto-switches to POST when
#             fields are present; an explicit GET keeps fields allowed).
#
# Path normalization: // -> / and /./ -> / so bypasses like //mnt/data,
# /mnt/./data, //, /./ are caught. Does NOT resolve .. (the one .. case
# tested, /mnt/data/.., is caught by the raw prefix match on /mnt/data).
#
# /mnt/data matching is structural, not co-occurrence: the command is split
# into subcommands on ; & | and newlines first, then within each segment the
# /mnt/data path must be an argument to the delete verb (or the search path
# of a `find ... -delete`). This prevents false positives where the verb and
# /mnt/data appear as unrelated words (e.g. inside a `git commit -m` message,
# or across an `&&` boundary: `rm /tmp/x && echo /mnt/data done`).
set -euo pipefail
set -f  # disable pathname expansion: tokens=(...) and s=(...) must not glob /*

cmd=$(jq -r '.tool_input.command // ""')
# Empty / missing command: nothing to enforce, stay silent.
[ -n "$cmd" ] || exit 0

# Collapse backslash-newline continuations BEFORE segmenting, so
# `gh api -X \<newline> DELETE` can't split a flag from its value across a
# segment boundary. Collapsing to a space preserves shell semantics.
# Quoted variable patterns keep backslash matching consistent across Bash versions.
line_continuation=$'\\\n'
cmd="${cmd//"$line_continuation"/ }"

deny() {
    local reason="$1"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$reason"
    exit 0
}

# Cheap pre-check: skip unless something relevant is mentioned. Uses word
# boundaries (\< \>) so verbs match at the start of the command, after
# whitespace, or after shell metachars (quotes, parens) - not just after
# whitespace.
if ! echo "$cmd" | grep -qE 'aws[[:space:]]+s3(api)?[[:space:]]|/mnt|\<(rm|rmdir|shred|unlink|trash|find|sudo|dd|mkfs|chmod)\>|\<git\>.*\<(push|api)\>|gh[[:space:]]+api|\<kubectl\>|\<k\>'; then
    exit 0
fi

# Path normalization: collapse // -> / and /./ -> /.
normalize_path() {
    local p="$1"
    p="${p//\/\///}"
    p="${p//\/\.\///}"
    p="${p%%/.}"
    printf '%s' "$p"
}

# Flatten shell quote / subshell / separator / backslash chars to spaces so
# wrapped forms (bash -c "aws s3 rm ...", $(aws s3 rm ...), a && aws s3 rm ...,
# \rm -rf ...) tokenize into bare tokens.
norm="${cmd//[\"\'\`\$\(\)\;\&\|\\]/ }"
# shellcheck disable=SC2206
tokens=($norm)
n=${#tokens[@]}

# ---------- command-level guards (flattened tokens) ----------

# sudo: deny anywhere in the command.
i=0
while (( i < n )); do
    if [[ "${tokens[i]}" == "sudo" ]]; then
        deny "Blocked: sudo is not permitted. sudo is not permitted for the agent - run it yourself outside Claude. (hook: check-bash-guard.sh)"
    fi
    i=$((i + 1))
done

# dd: deny anywhere (destructive disk operations).
i=0
while (( i < n )); do
    if [[ "${tokens[i]}" == "dd" ]]; then
        deny "Blocked: dd is not permitted. dd is not permitted for the agent - destructive disk operations. (hook: check-bash-guard.sh)"
    fi
    i=$((i + 1))
done

# mkfs: deny any token starting with mkfs (mkfs.ext4, mkfs.btrfs, ...).
i=0
while (( i < n )); do
    if [[ "${tokens[i]}" == mkfs* ]]; then
        deny "Blocked: mkfs is not permitted. mkfs is not permitted for the agent - destructive disk operations. (hook: check-bash-guard.sh)"
    fi
    i=$((i + 1))
done

# ---------- kubectl guard ----------
# kubectl|k with a mutating subcommand -> deny (read-only policy). Value-taking
# global flags (those that consume the next token as their value) are skipped as
# a pair so `kubectl -n kube-system delete pod foo` finds `delete`, not
# `kube-system`. Boolean flags and =value forms (--kubeconfig=...) are single
# tokens already skipped by the -?* flag skip. exec is NOT denied (the kubectl
# skill guides the agent to read-only use inside exec). rollout is special:
# `rollout status` is read-only (allowed); rollout restart/undo/pause/resume
# mutate (denied) - so when the verb is `rollout`, the next non-flag token is
# inspected.
KUBECTL_VERBS="delete deletecollection drain edit apply create patch replace scale set expose autoscale run label annotate cordon uncordon taint cp"
KUBECTL_ROLLOUT_DENY="restart undo pause resume"
KUBECTL_VALUE_FLAGS="-n --namespace --context --kubeconfig --cluster --user --server -s"
i=0
while (( i < n )); do
    if [[ "${tokens[i]}" == "kubectl" || "${tokens[i]}" == "k" ]]; then
        j=$((i + 1))
        while (( j < n )); do
            t="${tokens[j]}"
            # value-taking flag: skip the flag AND its value token.
            if [[ " $KUBECTL_VALUE_FLAGS " == *" $t "* ]]; then
                j=$((j + 2))
                continue
            fi
            # any other flag (-x, --x, --x=y, -xy): skip it alone.
            if [[ "$t" == -?* ]]; then
                j=$((j + 1))
                continue
            fi
            break
        done
        (( j < n )) || { i=$((i + 1)); continue; }
        sub="${tokens[j]}"
        case "$sub" in
            delete|deletecollection|drain|edit|apply|create|patch|replace|scale|set|expose|autoscale|run|label|annotate|cordon|uncordon|taint|cp)
                deny "Blocked: kubectl ${sub} mutates cluster resources. kubectl mutation verbs are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                ;;
            rollout)
                # rollout sub-verb: find next non-flag token; deny if it mutates.
                rj=$((j + 1))
                while (( rj < n )) && [[ "${tokens[rj]}" == -?* ]]; do
                    rj=$((rj + 1))
                done
                if (( rj < n )); then
                    rsub="${tokens[rj]}"
                    if [[ " $KUBECTL_ROLLOUT_DENY " == *" $rsub "* ]]; then
                        deny "Blocked: kubectl rollout ${rsub} mutates cluster resources. kubectl mutation verbs are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                    fi
                fi
                ;;
        esac
    fi
    i=$((i + 1))
done

# ---------- S3 guard ----------
# aws s3 rm|rb           -> deny (destructive s3 subcommands)
# aws s3 sync --delete   -> deny (--delete removes dest files absent from source)
# aws s3api delete-*     -> deny (the delete-* family)
# Flags between aws and s3/s3api are skipped so `aws --profile=p s3 rm ...` is caught.
i=0
while (( i < n )); do
    if [[ "${tokens[i]}" == "aws" ]]; then
        # Skip flag tokens (--*) between aws and s3/s3api.
        j=$((i + 1))
        while (( j < n )) && [[ "${tokens[j]}" == --* ]]; do
            j=$((j + 1))
        done
        (( j < n )) || { i=$((i + 1)); continue; }

        if [[ "${tokens[j]}" == "s3" ]]; then
            sub="${tokens[j+1]:-}"
            case "$sub" in
                rm|rb)
                    deny "Blocked: aws s3 ${sub} deletes S3 data. S3 deletes are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                    ;;
                sync)
                    k=$((j + 2))
                    while (( k < n )); do
                        if [[ "${tokens[k]}" == "--delete" ]]; then
                            deny "Blocked: aws s3 sync --delete removes S3 objects. S3 deletes are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                        fi
                        k=$((k + 1))
                    done
                    ;;
            esac
        elif [[ "${tokens[j]}" == "s3api" ]]; then
            sub="${tokens[j+1]:-}"
            if [[ "$sub" == delete-* ]]; then
                deny "Blocked: aws s3api ${sub} deletes S3 data. S3 deletes are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
            fi
        fi
    fi
    i=$((i + 1))
done

# ---------- /mnt/data guard ----------
# Split the command into subcommands on ; & | and newlines first, so a verb's
# args can't leak across a boundary. Within each segment, flatten only
# quote/subshell chars (NOT separators) and tokenize. The verb's args are
# then bounded to its own segment.
sep_re=$'[\n;&|]'
segs=()
while IFS= read -r seg || [ -n "$seg" ]; do
    [ -n "$seg" ] && segs+=("$seg")
done < <(printf '%s' "${cmd//$sep_re/$'\n'}")

for seg in "${segs[@]}"; do
    s_norm="${seg//[\"\'\`\$\(\)\\]/ }"
    # shellcheck disable=SC2206
    s=($s_norm)
    sn=${#s[@]}
    [ "$sn" -eq 0 ] && continue

    # git push --force/-f: deny force push (exact --force, not
    # --force-with-lease). Short-flag clusters containing f (-f, -fq, -qf)
    # and +refspec (+main:main, unconditional force) count as force; long
    # flags (--*) other than --force pass. Git global flags before the
    # subcommand (-C <path>, -c <kv>, --git-dir=...) are skipped so
    # `git -C /repo push -f` is still recognized as a push. Bounded to this
    # segment so a `rm -f` later in a && chain can't false-trigger.
    si=0
    while (( si < sn )); do
        if [[ "${s[si]}" == "git" ]]; then
            # find git's subcommand token, skipping global flags and the
            # value token of value-taking flags
            sj=$((si + 1))
            while (( sj < sn )); do
                t="${s[sj]}"
                if [[ "$t" == "-C" || "$t" == "-c" || "$t" == "--git-dir" || "$t" == "--work-tree" || "$t" == "--namespace" || "$t" == "--exec-path" || "$t" == "--config-env" ]]; then
                    sj=$((sj + 2))
                    continue
                fi
                if [[ "$t" == -?* ]]; then
                    sj=$((sj + 1))
                    continue
                fi
                break
            done
            if (( sj < sn )) && [[ "${s[sj]}" == "push" ]]; then
                sk=$((sj + 1))
                while (( sk < sn )); do
                    t="${s[sk]}"
                    # --force exact; short-flag clusters containing f (-f,
                    # -fq, -qf); +refspec (+main:main = unconditional force)
                    if [[ "$t" == "--force" ]] || [[ "$t" != --* && "$t" == -*f* ]] || [[ "$t" == +* ]]; then
                        deny "Blocked: git push --force is not permitted. git push --force is not permitted for the agent - run it yourself outside Claude. (hook: check-bash-guard.sh)"
                    fi
                    sk=$((sk + 1))
                done
            fi
        fi
        si=$((si + 1))
    done

    # gh api write methods: deny DELETE/POST/PATCH/PUT (via -X/--method, incl.
    # attached forms -XDELETE/-X=DELETE/--method=DELETE), --input (sends a
    # request body, incl. --input=file), and request fields -f/-F/--raw-field/
    # --field (gh auto-switches the method to POST when fields are present,
    # incl. attached -fkey=value and shorthand clusters like -if). An explicit
    # GET method keeps fields allowed (gh's read pattern:
    # `gh api -X GET search/issues -f q=x`). Value tokens of value-taking
    # flags are skipped in both passes so a quoted value like
    # `--jq "-X GET"` can't fake an explicit GET. Bounded to this segment so
    # a `curl -X POST` or `--input` elsewhere in a && chain can't
    # false-trigger.
    si=0
    while (( si + 1 < sn )); do
        if [[ "${s[si]}" == "gh" && "${s[si+1]}" == "api" ]]; then
            # first pass: is an explicit GET method present?
            has_get=0
            sj=$((si + 2))
            while (( sj < sn )); do
                t="${s[sj]}"
                case "$t" in
                    -X|--method) [[ "${s[sj+1]:-}" == "GET" ]] && has_get=1 ;;
                    -X?*) m="${t#-X}"; [[ "${m#=}" == "GET" ]] && has_get=1 ;;
                    --method=?*) [[ "${t#--method=}" == "GET" ]] && has_get=1 ;;
                    -H|-t|-q|-p|-f|-F|--hostname|--cache|--template|--jq|--preview|--input|--raw-field|--field)
                        sj=$((sj + 1))
                        ;;
                    -[!-]*)
                        # shorthand cluster with a field flag: its value
                        # follows when the cluster ends in f/F
                        if [[ "$t" == *[fF]* && "$t" == *[fF] ]]; then
                            sj=$((sj + 1))
                        fi
                        ;;
                esac
                sj=$((sj + 1))
            done
            # second pass: write signals
            sj=$((si + 2))
            while (( sj < sn )); do
                t="${s[sj]}"
                case "$t" in
                    -X|--method)
                        method="${s[sj+1]:-}"
                        case "$method" in
                            DELETE|POST|PATCH|PUT)
                                deny "Blocked: gh api -X ${method} is a write method. gh api write methods are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                                ;;
                        esac
                        ;;
                    -X?*)
                        method="${t#-X}"; method="${method#=}"
                        case "$method" in
                            DELETE|POST|PATCH|PUT)
                                deny "Blocked: gh api ${t} is a write method. gh api write methods are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                                ;;
                        esac
                        ;;
                    --method=?*)
                        method="${t#--method=}"
                        case "$method" in
                            DELETE|POST|PATCH|PUT)
                                deny "Blocked: gh api ${t} is a write method. gh api write methods are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                                ;;
                        esac
                        ;;
                    --input|--input=?*)
                        deny "Blocked: gh api ${t} sends a request body. gh api write methods are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                        ;;
                    --raw-field|--field)
                        if (( ! has_get )); then
                            deny "Blocked: gh api ${t} adds request parameters (gh auto-switches the method to POST). gh api write methods are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                        fi
                        sj=$((sj + 1))
                        ;;
                    --raw-field=?*|--field=?*)
                        if (( ! has_get )); then
                            deny "Blocked: gh api ${t} adds request parameters (gh auto-switches the method to POST). gh api write methods are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                        fi
                        ;;
                    -H|-t|-q|-p|--hostname|--cache|--template|--jq|--preview)
                        sj=$((sj + 1))
                        ;;
                    -[!-]*)
                        if [[ "$t" == *[fF]* ]]; then
                            if (( ! has_get )); then
                                deny "Blocked: gh api ${t} adds request parameters (gh auto-switches the method to POST). gh api write methods are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                            fi
                            [[ "$t" == *[fF] ]] && sj=$((sj + 1))
                        fi
                        ;;
                esac
                sj=$((sj + 1))
            done
        fi
        si=$((si + 1))
    done

    # chmod 777: deny chmod with a 777-granting octal mode among its args in
    # THIS segment (777, 0777, 1777, ... - any octal whose low 9 bits are
    # 777; bounded so `chmod +x f && echo 777` can't false-trigger).
    si=0
    while (( si < sn )); do
        if [[ "${s[si]}" == "chmod" ]]; then
            sj=$((si + 1))
            while (( sj < sn )); do
                if [[ "${s[sj]}" =~ ^[0-7]*777$ ]]; then
                    deny "Blocked: chmod ${s[sj]} is not permitted. chmod 777 is not permitted for the agent - permission weakening. (hook: check-bash-guard.sh)"
                fi
                sj=$((sj + 1))
            done
        fi
        si=$((si + 1))
    done

    # rm|rmdir|shred|unlink|trash with a protected path among their args in
    # THIS segment. Flags are skipped so rearrangements (rm -rf, rm -r -f,
    # rm -fr) all match the same. Paths are normalized so //mnt/data,
    # /mnt/./data, //, /./ are caught.
    si=0
    while (( si < sn )); do
        st="${s[si]}"
        case "$st" in
            rm|rmdir|shred|unlink|trash)
                sj=$((si + 1))
                while (( sj < sn )); do
                    a="${s[sj]}"
                    if [[ "$a" != -?* ]]; then
                        norm_a="$(normalize_path "$a")"
                        if [[ "$norm_a" == /mnt/data* ]]; then
                            deny "Blocked: ${st} on a path under /mnt/data. Deletes under /mnt/data are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                        fi
                        if [[ "$norm_a" == "/" || "$norm_a" == "/*" ]]; then
                            deny "Blocked: ${st} on filesystem root. Deletes on filesystem root are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                        fi
                        if [[ "$norm_a" == "/mnt" ]]; then
                            deny "Blocked: ${st} on /mnt (parent of /mnt/data). Deletes on /mnt (parent of /mnt/data) are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                        fi
                    fi
                    sj=$((sj + 1))
                done
                ;;
        esac
        si=$((si + 1))
    done

    # find with a protected search path AND -delete/-exec rm/-ok rm in THIS segment.
    si=0
    while (( si < sn )); do
        if [[ "${s[si]}" == "find" ]]; then
            search_path=""
            sj=$((si + 1))
            while (( sj < sn )); do
                a="${s[sj]}"
                if [[ "$a" == -?* || "$a" == "!" || "$a" == "(" || "$a" == ")" ]]; then
                    break
                fi
                if [[ -z "$search_path" ]]; then
                    search_path="$a"
                fi
                sj=$((sj + 1))
            done
            norm_sp="$(normalize_path "$search_path")"
            if [[ "$norm_sp" == /mnt/data* ]]; then
                sk=$((si + 1))
                while (( sk < sn )); do
                    if [[ "${s[sk]}" == "-delete" || "${s[sk]}" == "--delete" ]]; then
                        deny "Blocked: find -delete on a path under /mnt/data. Deletes under /mnt/data are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                    fi
                    if [[ "${s[sk]}" == "-exec" || "${s[sk]}" == "-execdir" || "${s[sk]}" == "-ok" || "${s[sk]}" == "-okdir" ]]; then
                        sm=$((sk + 1))
                        while (( sm < sn && sm < sk + 6 )); do
                            if [[ "${s[sm]}" == "rm" ]]; then
                                deny "Blocked: find ${s[sk]} rm on a path under /mnt/data. Deletes under /mnt/data are not permitted for the agent - run them yourself outside Claude. (hook: check-bash-guard.sh)"
                            fi
                            sm=$((sm + 1))
                        done
                    fi
                    sk=$((sk + 1))
                done
            fi
            break
        fi
        si=$((si + 1))
    done
done

exit 0
