// Shared command policy. Passing decisions defer to the harness permission engine.
//
// Scope:
//   S3:       deletes only blocked. Uploads (cp ./x s3://..., s3api put-*) and
//             read ops (ls, cp download, sync download, list-*/get-*) allowed.
//   sudo/dd/mkfs, chmod 777, forced git push, gh api writes and kubectl
//   mutations are blocked by the command checks below.
//   /mnt/data: ALL deletes blocked (rm, rmdir, shred, unlink, trash,
//             find -delete, find -exec rm). Reads/writes allowed.
//
// Shell heuristics:
//   - S3 guard flattens shell separators + quote/subshell chars so wrapped
//     forms (bash -c "...", $(...), a && b) still match. Last-match-style scan
//     over a fixed 3-token sequence (aws s3 <sub>) prevents cross-boundary
//     leakage constructing a false match.
//   - /mnt/data guard splits on command separators FIRST, then within each
//     segment flattens only quote/subshell chars (NOT separators) and requires
//     /mnt/data to be an argument to the delete verb in the same segment. This
//     prevents false positives where the verb and /mnt/data appear as unrelated
//     words across a boundary (rm /tmp/x && echo cleaned /mnt/data done).
//
// Known limitation: a delete verb
// nested in a quoted flag VALUE (git commit -m "rm ... /mnt/data ...") is
// indistinguishable from a quoted wrapper that EXECUTES (bash -c "rm ...").
// Both are denied; the user rewords if hit.

const S3_REASON =
  "S3 deletes are not permitted for the agent - run them yourself outside the agent. (policy: command)"
const MNT_REASON =
  "Deletes under /mnt/data are not permitted for the agent - run them yourself outside the agent. (policy: command)"
const ROOT_REASON =
  "Deletes on filesystem root are not permitted for the agent - run them yourself outside the agent. (policy: command)"
const MNT_PARENT_REASON =
  "Deletes on /mnt (parent of /mnt/data) are not permitted for the agent - run them yourself outside the agent. (policy: command)"
const SUDO_REASON =
  "sudo is not permitted for the agent - run it yourself outside the agent. (policy: command)"
const DD_REASON =
  "dd is not permitted for the agent - destructive disk operations. (policy: command)"
const MKFS_REASON =
  "mkfs is not permitted for the agent - destructive disk operations. (policy: command)"
const CHMOD_REASON =
  "chmod 777 is not permitted for the agent - permission weakening. (policy: command)"
const GIT_FORCE_REASON =
  "git push --force is not permitted for the agent - run it yourself outside the agent. (policy: command)"
const GH_API_REASON =
  "gh api write methods are not permitted for the agent - run them yourself outside the agent. (policy: command)"
const KUBECTL_REASON =
  "kubectl mutation verbs are not permitted for the agent - run them yourself outside the agent. (policy: command)"

// The precheck operates on normalized text so continuations cannot hide a
// guarded command.
const PRECHECK = /aws\s+s3(api)?\s|\/mnt\b|\b(rm|rmdir|shred|unlink|trash|find|sudo|dd|mkfs|chmod)\b|\bgit\b.*\b(push|api)\b|\bgh\s+api\b|\bkubectl\b|\bk\b/

// S3 guard: flatten separators + quote/subshell/backslash chars so wrapped/compound
// forms (bash -c "...", $(...), a && b, \rm) tokenize to bare tokens.
const S3_FLATTEN = /["'`$()|;&\\]/g
// Segment: flatten only quote/subshell/backslash chars (NOT separators, which
// were already split on).
const SEG_FLATTEN = /["'`$()\\]/g
const SPLIT_SEPS = /[\n;&|]/
const DELETE_VERBS = new Set(["rm", "rmdir", "shred", "unlink", "trash"])
const GH_WRITE_METHODS = new Set(["DELETE", "POST", "PATCH", "PUT"])

// Collapse // -> / and /./ -> / so path-normalization bypasses (//mnt/data,
// /mnt/./data, //, /./) are caught. Does NOT resolve .. (the one .. case we
// tested, /mnt/data/.., is caught by the raw prefix match on /mnt/data).
function normalizePath(p) {
  return p.replace(/\/+/g, "/").replace(/\/\.\//g, "/").replace(/\/\.$/, "")
}

export function decide(command) {
  const allow = { deny: false }
  if (typeof command !== "string" || command === "") return allow

  // Collapse backslash-newline continuations BEFORE segmenting, so
  // `gh api -X \<newline> DELETE` can't split a flag from its value across a
  // segment boundary.
  command = command.replace(/\\\n/g, " ")
  if (!PRECHECK.test(command)) return allow

  // ---------- command-level guards (flattened tokens) ----------
  const tokens = command.replace(S3_FLATTEN, " ").split(/\s+/).filter(Boolean)
  const n = tokens.length

  // sudo: deny anywhere in the command (covers sudo rm, bash -c "sudo ...").
  if (tokens.includes("sudo")) {
    return { deny: true, reason: `Blocked: sudo is not permitted. ${SUDO_REASON}` }
  }

  // dd: deny anywhere (destructive disk operations).
  if (tokens.includes("dd")) {
    return { deny: true, reason: `Blocked: dd is not permitted. ${DD_REASON}` }
  }

  // mkfs: deny any token starting with mkfs (mkfs.ext4, mkfs.btrfs, ...).
  for (const t of tokens) {
    if (t.startsWith("mkfs")) {
      return { deny: true, reason: `Blocked: mkfs is not permitted. ${MKFS_REASON}` }
    }
  }

  // ---------- kubectl guard ----------
  // kubectl|k with a mutating subcommand -> deny (read-only policy). Value-
  // taking global flags (those that consume the next token as their value) are
  // skipped as a pair so `kubectl -n kube-system delete pod foo` finds `delete`,
  // not `kube-system`. Boolean flags and =value forms (--kubeconfig=...) are
  // single tokens already skipped by the -?* flag skip. exec is NOT denied (the
  // kubectl skill guides the agent to read-only use inside exec). rollout is
  // special: `rollout status` is read-only (allowed); rollout
  // restart/undo/pause/resume mutate (denied) - so when the verb is `rollout`,
  // the next non-flag token is inspected.
  const KUBECTL_VERBS = new Set([
    "delete", "deletecollection", "drain", "edit", "apply", "create",
    "patch", "replace", "scale", "set", "expose", "autoscale", "run",
    "label", "annotate", "cordon", "uncordon", "taint", "cp",
  ])
  const KUBECTL_ROLLOUT_DENY = new Set(["restart", "undo", "pause", "resume"])
  const KUBECTL_VALUE_FLAGS = new Set(["-n", "--namespace", "--context", "--kubeconfig", "--cluster", "--user", "--server", "-s"])
  for (let i = 0; i < n; i++) {
    if (tokens[i] !== "kubectl" && tokens[i] !== "k") continue
    let j = i + 1
    while (j < n) {
      const t = tokens[j]
      if (KUBECTL_VALUE_FLAGS.has(t)) { j += 2; continue }
      if (t.startsWith("-")) { j++; continue }
      break
    }
    if (j >= n) continue
    const sub = tokens[j]
    if (KUBECTL_VERBS.has(sub)) {
      return { deny: true, reason: `Blocked: kubectl ${sub} mutates cluster resources. ${KUBECTL_REASON}` }
    }
    if (sub === "rollout") {
      let rj = j + 1
      while (rj < n && tokens[rj].startsWith("-")) rj++
      if (rj < n && KUBECTL_ROLLOUT_DENY.has(tokens[rj])) {
        return { deny: true, reason: `Blocked: kubectl rollout ${tokens[rj]} mutates cluster resources. ${KUBECTL_REASON}` }
      }
    }
  }

  // ---------- S3 guard ----------
  // When we find `aws`, skip flag tokens (--*) before looking for s3/s3api,
  // so `aws --profile=p s3 rm ...` is caught.
  for (let i = 0; i < n; i++) {
    if (tokens[i] === "aws") {
      let j = i + 1
      while (j < n && tokens[j].startsWith("-")) j++
      if (j >= n) continue
      if (tokens[j] === "s3") {
        const sub = tokens[j + 1]
        if (sub === "rm" || sub === "rb") {
          return { deny: true, reason: `Blocked: aws s3 ${sub} deletes S3 data. ${S3_REASON}` }
        }
        if (sub === "sync") {
          for (let k = j + 2; k < n; k++) {
            if (tokens[k] === "--delete") {
              return { deny: true, reason: `Blocked: aws s3 sync --delete removes S3 objects. ${S3_REASON}` }
            }
          }
        }
      }
      if (tokens[j] === "s3api") {
        const sub = tokens[j + 1]
        if (sub && sub.startsWith("delete-")) {
          return { deny: true, reason: `Blocked: aws s3api ${sub} deletes S3 data. ${S3_REASON}` }
        }
      }
    }
  }

  // ---------- segment-based path guards ----------
  for (const seg of command.split(SPLIT_SEPS)) {
    if (!seg.trim()) continue
    const s = seg.replace(SEG_FLATTEN, " ").split(/\s+/).filter(Boolean)
    const sn = s.length
    if (sn === 0) continue

    // git push --force/-f: deny force push (exact --force, not
    // --force-with-lease). Short-flag clusters containing f (-f, -fq, -qf)
    // and +refspec (+main:main, unconditional force) count as force; long
    // flags (--*) other than --force pass. Git global flags before the
    // subcommand (-C <path>, -c <kv>, --git-dir=...) are skipped so
    // `git -C /repo push -f` is still recognized as a push. Bounded to this
    // segment so a `rm -f` later in a && chain can't false-trigger.
    const GIT_VALUE_FLAGS = new Set(["-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"])
    for (let si = 0; si < sn; si++) {
      if (s[si] !== "git") continue
      // find git's subcommand token, skipping global flags and the value
      // token of value-taking flags
      let sj = si + 1
      while (sj < sn) {
        const t = s[sj]
        if (GIT_VALUE_FLAGS.has(t)) { sj += 2; continue }
        if (t.startsWith("-")) { sj++; continue }
        break
      }
      if (sj < sn && s[sj] === "push") {
        for (let sk = sj + 1; sk < sn; sk++) {
          const t = s[sk]
          // --force exact; short-flag clusters containing f (-f, -fq, -qf);
          // +refspec (+main:main = unconditional force)
          if (t === "--force" || (!t.startsWith("--") && t.startsWith("-") && t.includes("f")) || t.startsWith("+")) {
            return { deny: true, reason: `Blocked: git push --force is not permitted. ${GIT_FORCE_REASON}` }
          }
        }
      }
    }

    // gh api write methods: deny DELETE/POST/PATCH/PUT (via -X/--method, incl.
    // attached forms -XDELETE/-X=DELETE/--method=DELETE), --input (sends a
    // request body, incl. --input=file), and request fields -f/-F/--raw-field/
    // --field (gh auto-switches the method to POST when fields are present,
    // incl. attached -fkey=value and shorthand clusters like -if). An explicit
    // GET method keeps fields allowed (gh's read pattern:
    // `gh api -X GET search/issues -f q=x`). Value tokens of value-taking
    // flags are skipped in both passes so a quoted value like
    // `--jq "-X GET"` can't fake an explicit GET. Bounded to this segment so
    // a `curl -X POST` or `--input` elsewhere in a && chain can't
    // false-trigger.
    const GH_VALUE_FLAGS = new Set(["-H", "-t", "-q", "-p", "--hostname", "--cache", "--template", "--jq", "--preview", "--input", "--raw-field", "--field"])
    const isFieldToken = (t) => t.startsWith("-") && !t.startsWith("--") && /[fF]/.test(t)
    for (let si = 0; si + 1 < sn; si++) {
      if (s[si] !== "gh" || s[si + 1] !== "api") continue
      // first pass: is an explicit GET method present?
      let hasGet = false
      for (let sj = si + 2; sj < sn; sj++) {
        const t = s[sj]
        if (t === "-X" || t === "--method") {
          if (s[sj + 1] === "GET") hasGet = true
        } else if (t.startsWith("-X")) {
          if (t.slice(2).replace(/^=/, "") === "GET") hasGet = true
        } else if (t.startsWith("--method=")) {
          if (t.slice(9) === "GET") hasGet = true
        } else if (GH_VALUE_FLAGS.has(t)) {
          sj++ // skip the flag's value token
        } else if (isFieldToken(t)) {
          // shorthand cluster with a field flag: its value follows when the
          // cluster ends in f/F
          if ( /[fF]$/.test(t)) sj++
        }
      }
      // second pass: write signals
      for (let sj = si + 2; sj < sn; sj++) {
        const t = s[sj]
        if (t === "-X" || t === "--method") {
          const method = s[sj + 1]
          if (method && GH_WRITE_METHODS.has(method)) {
            return { deny: true, reason: `Blocked: gh api -X ${method} is a write method. ${GH_API_REASON}` }
          }
        } else if (t.startsWith("-X")) {
          const method = t.slice(2).replace(/^=/, "")
          if (GH_WRITE_METHODS.has(method)) {
            return { deny: true, reason: `Blocked: gh api ${t} is a write method. ${GH_API_REASON}` }
          }
        } else if (t.startsWith("--method=")) {
          const method = t.slice(9)
          if (GH_WRITE_METHODS.has(method)) {
            return { deny: true, reason: `Blocked: gh api ${t} is a write method. ${GH_API_REASON}` }
          }
        } else if (t === "--input" || t.startsWith("--input=")) {
          return { deny: true, reason: `Blocked: gh api ${t} sends a request body. ${GH_API_REASON}` }
        } else if (t === "--raw-field" || t === "--field") {
          if (!hasGet) {
            return { deny: true, reason: `Blocked: gh api ${t} adds request parameters (gh auto-switches the method to POST). ${GH_API_REASON}` }
          }
          sj++ // skip the flag's value token
        } else if (t.startsWith("--raw-field=") || t.startsWith("--field=")) {
          if (!hasGet) {
            return { deny: true, reason: `Blocked: gh api ${t} adds request parameters (gh auto-switches the method to POST). ${GH_API_REASON}` }
          }
        } else if (GH_VALUE_FLAGS.has(t)) {
          sj++ // skip the flag's value token
        } else if (isFieldToken(t)) {
          if (!hasGet) {
            return { deny: true, reason: `Blocked: gh api ${t} adds request parameters (gh auto-switches the method to POST). ${GH_API_REASON}` }
          }
          if (/[fF]$/.test(t)) sj++ // cluster ends in the field flag: value follows
        }
      }
    }

    // chmod 777: deny chmod with a 777-granting octal mode among its args in
    // THIS segment (777, 0777, 1777, ... - any octal whose low 9 bits are
    // 777; bounded so `chmod +x f && echo 777` can't false-trigger).
    for (let si = 0; si < sn; si++) {
      if (s[si] === "chmod") {
        for (let sj = si + 1; sj < sn; sj++) {
          if (/^[0-7]*777$/.test(s[sj])) {
            return { deny: true, reason: `Blocked: chmod ${s[sj]} is not permitted. ${CHMOD_REASON}` }
          }
        }
      }
    }

    // rm|rmdir|shred|unlink|trash with a protected path among their args in
    // THIS segment. Flags are skipped so rearrangements (rm -rf, rm -r -f,
    // rm -fr) all match the same. Paths are normalized before matching so
    // //mnt/data, /mnt/./data, //, /./ are caught.
    for (let si = 0; si < sn; si++) {
      const verb = s[si]
      if (DELETE_VERBS.has(verb)) {
        for (let sj = si + 1; sj < sn; sj++) {
          const a = s[sj]
          if (a.startsWith("-")) continue
          const norm = normalizePath(a)
          if (norm.startsWith("/mnt/data")) {
            return { deny: true, reason: `Blocked: ${verb} on a path under /mnt/data. ${MNT_REASON}` }
          }
          if (norm === "/" || norm === "/*") {
            return { deny: true, reason: `Blocked: ${verb} on filesystem root. ${ROOT_REASON}` }
          }
          if (norm === "/mnt") {
            return { deny: true, reason: `Blocked: ${verb} on /mnt (parent of /mnt/data). ${MNT_PARENT_REASON}` }
          }
        }
      }
    }

    // find with a protected search path AND -delete/-exec rm/-ok rm in THIS segment.
    for (let si = 0; si < sn; si++) {
      if (s[si] !== "find") continue
      let searchPath = ""
      let sj = si + 1
      while (sj < sn) {
        const a = s[sj]
        if ((a.startsWith("-") && a.length >= 2) || a === "!" || a === "(" || a === ")") break
        if (!searchPath) searchPath = a
        sj++
      }
      const normPath = normalizePath(searchPath)
      if (normPath.startsWith("/mnt/data")) {
        for (let sk = si + 1; sk < sn; sk++) {
          if (s[sk] === "-delete" || s[sk] === "--delete") {
            return { deny: true, reason: `Blocked: find -delete on a path under /mnt/data. ${MNT_REASON}` }
          }
          if (s[sk] === "-exec" || s[sk] === "-execdir" || s[sk] === "-ok" || s[sk] === "-okdir") {
            for (let sm = sk + 1; sm < sn && sm < sk + 6; sm++) {
              if (s[sm] === "rm") {
                return { deny: true, reason: `Blocked: find ${s[sk]} rm on a path under /mnt/data. ${MNT_REASON}` }
              }
            }
          }
        }
      }
      break
    }
  }

  return allow
}
