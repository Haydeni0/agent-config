// Shared command policy. Passing decisions defer to the harness permission engine.
//
// Scope:
//   S3:       deletes only blocked (s3 rm, s3 rb, s3 sync --delete, s3api
//             delete-*). Uploads (cp ./x s3://..., s3api put-*) and read ops
//             (ls, cp download, sync download, list-*/get-*) allowed.
//   sudo/dd/mkfs, chmod 777, forced git push, gh api writes and kubectl
//   mutations are blocked by the guards below.
//   Git gate: commit-creating subcommands (commit, merge, cherry-pick,
//   revert, rebase, am, pull without --ff-only) need COMMIT_AUTHORISED,
//   push and gh pr merge need PUSH_AUTHORISED (pr merge needs both);
//   COMMIT_UNAUTHORISED/PUSH_UNAUTHORISED deny despite a set authorise var.
//   Protected paths: /mnt/data and everything under it, filesystem root,
//             and /mnt, in any literal absolute spelling (//, /./, trailing
//             /, .. resolved lexically, a glob or brace pattern that can name
//             /mnt or /mnt/data). Deletes on them are blocked for the delete verbs (rm,
//             rmdir, shred, unlink, trash) and for a find carrying a delete
//             action (-delete, or -exec/-execdir/-ok/-okdir with a delete
//             verb). Reads/writes allowed.
//
// Shell heuristics:
//   - Every command is read in two views and denies when either denies. The
//     flattened view (below) sees inside wrapper strings; the quoted view
//     keeps a quoted span inside one word, so a blank in an option value
//     (git -c "a b" push) cannot shift the subcommand position, and re-lexes
//     quoted words holding a blank as nested commands.
//   - Tool names match by basename (/usr/bin/git is git).
//   - fd-duplicating redirections (2>&1, >&2, &>) are blanked before
//     segmenting, so their & does not split a command from its own flags.
//   - Flattened view: command-token guards (sudo, dd, mkfs, kubectl, S3) flatten shell
//     separators + quote/subshell chars so wrapped forms (bash -c "...",
//     $(...), a && b) still match.
//   - Segment guards (git, gh, chmod, delete verbs, find) split on command
//     separators FIRST, then within each segment flatten only quote/subshell
//     chars (NOT separators), so a verb and a path must share a segment. This
//     prevents false positives where they appear as unrelated words across a
//     boundary (rm /tmp/x && echo cleaned /mnt/data done).
//   - Subcommands are found past global options: a value-taking option skips
//     its value token too. aws also accepts unambiguous option-name prefixes
//     (--prof p) and options between s3/s3api and the subcommand, so both
//     positions use the aws option table with prefix matching.
//   - find takes search paths anywhere on the line (bfs), so a deleting find
//     denies when ANY non-option token after find is a protected path.
//
// Known limitations:
//   - A delete verb nested in a quoted flag VALUE (git commit -m "rm ...
//     /mnt/data ...") is indistinguishable from a quoted wrapper that
//     EXECUTES (bash -c "rm ..."). Both are denied; the user rewords if hit.
//     The same covers a git gate verb nested in a quoted flag value (git
//     commit -m "then git push") - denied on the safe side.
//   - A deleting find that merely mentions a protected path as an operand of
//     a test (find /tmp -newer /mnt/data/ref -delete) is denied on the safe
//     side.
//   - A glob pattern is matched per path component against mnt and data, so
//     one that names a different directory with the same spelling (/m* also
//     names /media) is denied on the safe side.

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
const GIT_GATE_TAIL =
  "The user sets it in their session - run it yourself outside the agent if it must happen now. (policy: command)"
const COMMIT_SUBCOMMANDS = new Set(["commit", "merge", "cherry-pick", "revert", "rebase", "am"])

// Command tokens: flatten separators + quote/subshell/backslash chars so
// wrapped/compound forms (bash -c "...", $(...), a && b, \rm) tokenize to bare
// tokens.
const S3_FLATTEN = /["'`$()|;&\\]/g
// Segment: flatten only quote/subshell/backslash chars (NOT separators, which
// were already split on).
const SEG_FLATTEN = /["'`$()\\]/g
const SPLIT_SEPS = /[\n;&|]/
// Match Bash's default IFS; Unicode whitespace stays inside argument values.
const SHELL_WHITESPACE = /[ \t\n]+/
const DELETE_VERBS = new Set(["rm", "rmdir", "shred", "unlink", "trash"])
// Tool names match by basename so a path-qualified invocation (/bin/rm,
// /usr/bin/git) is the same tool. Reasons name the basename.
const toolName = (t) => t.slice(t.lastIndexOf("/") + 1)
const GH_WRITE_METHODS = new Set(["DELETE", "POST", "PATCH", "PUT"])
const KUBECTL_VERBS = new Set([
  "delete", "deletecollection", "drain", "edit", "apply", "create",
  "patch", "replace", "scale", "set", "expose", "autoscale", "run",
  "label", "annotate", "cordon", "uncordon", "taint", "cp",
])
const KUBECTL_ROLLOUT_DENY = new Set(["restart", "undo", "pause", "resume"])
const FIND_EXEC_ACTIONS = new Set(["-exec", "-execdir", "-ok", "-okdir"])
// Wrapper-string levels the quoted view re-lexes, one per wrapper (sh -c "..." is 1).
const NESTED_COMMAND_DEPTH = 3
// Brace expansions examined per path before the path counts as protected.
const MAX_BRACE_EXPANSIONS = 64
// Bash sequence expression inside a brace: {a..c}, {1..10}, {1..10..2}.
const BRACE_SEQUENCE = /\{[^{},/]*\.\.[^{},/]*\}/g
// fd-duplicating redirections (2>&1, >&2, <&0, >&-, &>, &>>): their & is not
// a command separator.
const FD_REDIRECT = /\d*[<>]&(?:\d+|-)?|&>>?/g
// find exec delete: a delete verb must appear within this many tokens after the action
// (covers `-exec sh -c rm ...`-style wrappers without scanning the whole line).
const FIND_EXEC_RM_WINDOW = 5
// gh api flags whose value is the next token, skipped so a quoted value like
// `--jq "-X GET"` can't fake a method.
const GH_API_VALUE_FLAGS = new Set(["-H", "-t", "-q", "-p", "--hostname", "--cache", "--template", "--jq", "--preview", "--input", "--raw-field", "--field"])

// Option tables for findSubcommand. `value`: options that consume the next
// token. `prefixes`: the tool accepts unambiguous option-name prefixes.
const KUBECTL_OPTIONS = {
  value: new Set(["-n", "--namespace", "--context", "--kubeconfig", "--cluster", "--user", "--server", "-s"]),
  prefixes: false,
}
// Value-taking global options of aws-cli 2.35.10 (awscli/data/cli.json); also
// accepted between s3/s3api and the subcommand.
const AWS_OPTIONS = {
  value: new Set([
    "--profile", "--region", "--endpoint-url", "--output", "--query", "--color",
    "--ca-bundle", "--cli-read-timeout", "--cli-connect-timeout",
    "--cli-binary-format", "--cli-error-format",
  ]),
  prefixes: true,
}
const GIT_OPTIONS = {
  value: new Set(["-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"]),
  prefixes: false,
}
const GH_OPTIONS = { value: new Set(["-R", "--repo", "--hostname"]), prefixes: false }

// Returns a deny reason when the gate blocks, null when authorized. A set
// revoke var denies even when the authorise var is set.
function gitGateReason(env, sub, kind) {
  const authVar = kind === "commit" ? "COMMIT_AUTHORISED" : "PUSH_AUTHORISED"
  const revokeVar = kind === "commit" ? "COMMIT_UNAUTHORISED" : "PUSH_UNAUTHORISED"
  if (env?.[revokeVar]) {
    return `Blocked: ${sub} is revoked - ${revokeVar} is set in this session. The user clears it in their session. (policy: command)`
  }
  if (!env?.[authVar]) {
    return `Blocked: ${sub} needs ${authVar}, which is not set. ${GIT_GATE_TAIL}`
  }
  return null
}

// Collapse // and /./ and drop a trailing / or /. so every spelling of one
// directory compares equal (//mnt/data, /mnt/./data, /mnt/, /., //). `..` is
// not resolved: /mnt/data/.. still matches the /mnt/data prefix.
function normalizePath(p) {
  const collapsed = p.replace(/\/+/g, "/").replace(/(\/\.)+(?=\/|$)/g, "")
  if (collapsed === "" && p.startsWith("/")) return "/"
  return collapsed.length > 1 ? collapsed.replace(/\/$/, "") : collapsed
}

// Bash brace expansion of `p` ({a,b} and nesting; a brace without a top-level
// comma stays literal). null past MAX_BRACE_EXPANSIONS, which callers treat as
// protected.
function expandBraces(p) {
  const open = p.indexOf("{")
  if (open === -1) return [p]
  let depth = 0
  let close = -1
  const commas = []
  for (let i = open; i < p.length && close === -1; i++) {
    if (p[i] === "{") depth++
    else if (p[i] === "}" && --depth === 0) close = i
    else if (p[i] === "," && depth === 1) commas.push(i)
  }
  if (close === -1 || commas.length === 0) return [p]
  const head = p.slice(0, open)
  const tail = p.slice(close + 1)
  const out = []
  let start = open + 1
  for (const end of [...commas, close]) {
    const expanded = expandBraces(head + p.slice(start, end) + tail)
    if (expanded === null) return null
    out.push(...expanded)
    if (out.length > MAX_BRACE_EXPANSIONS) return null
    start = end + 1
  }
  return out
}

// Whether one glob path component can match `name`. A bracket expression
// counts as any one character; one holding `[` or `\\` (POSIX, equivalence and
// collating classes), or followed later by another `]` (an escaped `]` whose
// backslash the lexer removed), makes the whole component match, so the
// answer only errs toward matching.
function globComponentMatches(pattern, name) {
  let source = ""
  for (let i = 0; i < pattern.length; i++) {
    const c = pattern[i]
    const classEnd = c === "[" ? pattern.indexOf("]", i + 2) : -1
    if (c === "*") source += ".*"
    else if (c === "?") source += "."
    else if (classEnd !== -1) {
      if (/[[\\]/.test(pattern.slice(i + 1, classEnd)) || pattern.includes("]", classEnd + 1)) return true
      source += "."
      i = classEnd
    } else source += c.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  }
  return new RegExp(`^${source}$`).test(name)
}

// Reason for an absolute glob or brace pattern that can name /mnt or a path
// at or under /mnt/data; null when it cannot or is not a pattern. A sequence
// expression ({a..c}, {1..9..2}) counts as `*`; each expansion is checked
// with `..` resolved.
function globReason(label, norm) {
  if (!norm.startsWith("/") || !/[*?[{]/.test(norm)) return null
  const expansions = expandBraces(norm.replace(BRACE_SEQUENCE, "*"))
  if (expansions === null) return `Blocked: ${label} on /mnt (parent of /mnt/data). ${MNT_PARENT_REASON}`
  for (const expansion of expansions) {
    const path = resolveDotDot(normalizePath(expansion))
    if (!/[*?[]/.test(path)) {
      const reason = expansion === norm ? null : protectedReason(label, path)
      if (reason) return reason
      continue
    }
    const [first, second] = path.split("/").slice(1)
    if (!globComponentMatches(first, "mnt")) continue
    if (second === undefined) return `Blocked: ${label} on /mnt (parent of /mnt/data). ${MNT_PARENT_REASON}`
    if (globComponentMatches(second, "data")) return `Blocked: ${label} on a path under /mnt/data. ${MNT_REASON}`
  }
  return null
}

// Index of the first token at or after `start` that is neither an option nor
// an option's value; tokens.length when none. A bare `--` is a one-token skip.
function findSubcommand(tokens, start, options) {
  let j = start
  while (j < tokens.length) {
    const t = tokens[j]
    if (options.value.has(t) || (options.prefixes && isValueOptionPrefix(t, options.value))) {
      j += 2
      continue
    }
    if (t.startsWith("-")) {
      j++
      continue
    }
    return j
  }
  return tokens.length
}

// aws-cli rejects ambiguous prefixes, so a prefix that names a value option in
// a running command names exactly that option.
function isValueOptionPrefix(t, valueOptions) {
  if (t.length <= 2 || !t.startsWith("--") || t.includes("=")) return false
  for (const option of valueOptions) if (option.startsWith(t)) return true
  return false
}

// Lexically resolve `..` in an absolute normalized path (/tmp/../mnt -> /mnt,
// /.. -> /).
function resolveDotDot(norm) {
  if (!norm.startsWith("/")) return norm
  const parts = []
  for (const part of norm.split("/").slice(1)) {
    if (part === "..") parts.pop()
    else parts.push(part)
  }
  return "/" + parts.join("/")
}

// Checks the path as written, then with `..` resolved, so both
// /mnt/data/.. and /tmp/../mnt/data deny.
function protectedPathReason(label, arg) {
  const norm = normalizePath(arg)
  return protectedReason(label, norm) ?? protectedReason(label, resolveDotDot(norm))
}

// Protected: /mnt/data and below, filesystem root (/ and /*), /mnt, and any
// absolute glob or brace pattern that can name /mnt or /mnt/data.
function protectedReason(label, norm) {
  if (norm.startsWith("/mnt/data")) return `Blocked: ${label} on a path under /mnt/data. ${MNT_REASON}`
  if (norm === "/" || norm === "/*") return `Blocked: ${label} on filesystem root. ${ROOT_REASON}`
  if (norm === "/mnt") return `Blocked: ${label} on /mnt (parent of /mnt/data). ${MNT_PARENT_REASON}`
  return globReason(label, norm)
}

// ---------- command-token guards: (tokens, env) -> reason | null ----------

// sudo anywhere in the command (covers sudo rm, bash -c "sudo ...").
function sudoGuard(tokens) {
  return tokens.some((t) => toolName(t) === "sudo") ? `Blocked: sudo is not permitted. ${SUDO_REASON}` : null
}

function ddGuard(tokens) {
  return tokens.some((t) => toolName(t) === "dd") ? `Blocked: dd is not permitted. ${DD_REASON}` : null
}

// mkfs and its mkfs.<fs> variants; word-boundary so mkfs_tool/mkfsx pass.
function mkfsGuard(tokens) {
  return tokens.some((t) => /^mkfs\b/.test(t) || /^mkfs\b/.test(toolName(t))) ? `Blocked: mkfs is not permitted. ${MKFS_REASON}` : null
}

// kubectl|k with a mutating verb (read-only policy). exec is NOT denied (the
// kubectl skill guides the agent to read-only use inside exec). rollout
// status is read-only; rollout restart/undo/pause/resume mutate.
function kubectlGuard(tokens) {
  for (let i = 0; i < tokens.length; i++) {
    const name = toolName(tokens[i])
    if (name !== "kubectl" && name !== "k") continue
    const j = findSubcommand(tokens, i + 1, KUBECTL_OPTIONS)
    const verb = tokens[j]
    if (KUBECTL_VERBS.has(verb)) {
      return `Blocked: kubectl ${verb} mutates cluster resources. ${KUBECTL_REASON}`
    }
    if (verb === "rollout") {
      const action = tokens[findSubcommand(tokens, j + 1, KUBECTL_OPTIONS)]
      if (KUBECTL_ROLLOUT_DENY.has(action)) {
        return `Blocked: kubectl rollout ${action} mutates cluster resources. ${KUBECTL_REASON}`
      }
    }
  }
  return null
}

function s3Guard(tokens) {
  for (let i = 0; i < tokens.length; i++) {
    if (toolName(tokens[i]) !== "aws") continue
    const j = findSubcommand(tokens, i + 1, AWS_OPTIONS)
    const service = tokens[j]
    if (service !== "s3" && service !== "s3api") continue
    const k = findSubcommand(tokens, j + 1, AWS_OPTIONS)
    const sub = tokens[k]
    if (service === "s3api") {
      if (sub?.startsWith("delete-")) return `Blocked: aws s3api ${sub} deletes S3 data. ${S3_REASON}`
      continue
    }
    if (sub === "rm" || sub === "rb") return `Blocked: aws s3 ${sub} deletes S3 data. ${S3_REASON}`
    if (sub === "sync" && tokens.slice(k + 1).some(isDeleteOptionPrefix)) {
      return `Blocked: aws s3 sync --delete removes S3 objects. ${S3_REASON}`
    }
  }
  return null
}

// --delete or an unambiguous aws prefix of it (--del, --dele, ...).
function isDeleteOptionPrefix(t) {
  return t.startsWith("--del") && "--delete".startsWith(t)
}

// ---------- segment guards: (segment tokens, env) -> reason | null ----------

// git push --force/-f (exact --force, not --force-with-lease; short clusters
// containing f; +refspec), then the push/commit gate. --ff-only pull is exempt.
function gitGuard(s, env) {
  for (let i = 0; i < s.length; i++) {
    if (toolName(s[i]) !== "git") continue
    const j = findSubcommand(s, i + 1, GIT_OPTIONS)
    const sub = s[j]
    let gate = null
    if (sub === "push") {
      for (const t of s.slice(j + 1)) {
        if (t === "--force" || (!t.startsWith("--") && t.startsWith("-") && t.includes("f")) || t.startsWith("+")) {
          return `Blocked: git push --force is not permitted. ${GIT_FORCE_REASON}`
        }
      }
      gate = gitGateReason(env, "git push", "push")
    } else if (COMMIT_SUBCOMMANDS.has(sub)) {
      gate = gitGateReason(env, `git ${sub}`, "commit")
    } else if (sub === "pull" && !s.slice(j + 1).includes("--ff-only")) {
      gate = gitGateReason(env, "git pull", "commit")
    }
    if (gate) return gate
  }
  return null
}

// gh pr merge needs both gates (merge commit + remote update); gh api write
// signals are denied.
function ghGuard(s, env) {
  for (let i = 0; i < s.length; i++) {
    if (toolName(s[i]) !== "gh") continue
    const j = findSubcommand(s, i + 1, GH_OPTIONS)
    if (s[j] === "pr" && s[j + 1] === "merge") {
      const gate = gitGateReason(env, "gh pr merge", "commit") ?? gitGateReason(env, "gh pr merge", "push")
      if (gate) return gate
    }
    if (s[j] !== "api") continue
    const reason = ghApiWriteReason(s, j + 1)
    if (reason) return reason
  }
  return null
}

const isGhFieldCluster = (t) => t.startsWith("-") && !t.startsWith("--") && /[fF]/.test(t)

// gh api write signals: DELETE/POST/PATCH/PUT via -X/--method (incl. attached
// -XDELETE/-X=DELETE/--method=DELETE), --input (request body, incl.
// --input=file), and request fields -f/-F/--raw-field/--field (gh switches the
// method to POST when fields are present, incl. attached -fkey=value and
// clusters like -if). An explicit GET keeps fields allowed (gh's read pattern:
// `gh api -X GET search/issues -f q=x`). Value tokens of value-taking flags are
// skipped in both passes so a quoted value like `--jq "-X GET"` can't fake an
// explicit GET.
function ghApiWriteReason(s, start) {
  let hasGet = false
  for (let i = start; i < s.length; i++) {
    const t = s[i]
    if (t === "-X" || t === "--method") {
      if (s[i + 1] === "GET") hasGet = true
    } else if (t.startsWith("-X")) {
      if (t.slice(2).replace(/^=/, "") === "GET") hasGet = true
    } else if (t.startsWith("--method=")) {
      if (t.slice(9) === "GET") hasGet = true
    } else if (GH_API_VALUE_FLAGS.has(t)) {
      i++
    } else if (isGhFieldCluster(t)) {
      if (/[fF]$/.test(t)) i++ // cluster ends in the field flag: value follows
    }
  }
  const fieldReason = (t) =>
    `Blocked: gh api ${t} adds request parameters (gh auto-switches the method to POST). ${GH_API_REASON}`
  for (let i = start; i < s.length; i++) {
    const t = s[i]
    if (t === "-X" || t === "--method") {
      const method = s[i + 1]
      if (GH_WRITE_METHODS.has(method)) return `Blocked: gh api -X ${method} is a write method. ${GH_API_REASON}`
    } else if (t.startsWith("-X")) {
      if (GH_WRITE_METHODS.has(t.slice(2).replace(/^=/, ""))) return `Blocked: gh api ${t} is a write method. ${GH_API_REASON}`
    } else if (t.startsWith("--method=")) {
      if (GH_WRITE_METHODS.has(t.slice(9))) return `Blocked: gh api ${t} is a write method. ${GH_API_REASON}`
    } else if (t === "--input" || t.startsWith("--input=")) {
      return `Blocked: gh api ${t} sends a request body. ${GH_API_REASON}`
    } else if (t === "--raw-field" || t === "--field") {
      if (!hasGet) return fieldReason(t)
      i++
    } else if (t.startsWith("--raw-field=") || t.startsWith("--field=")) {
      if (!hasGet) return fieldReason(t)
    } else if (GH_API_VALUE_FLAGS.has(t)) {
      i++
    } else if (isGhFieldCluster(t)) {
      if (!hasGet) return fieldReason(t)
      if (/[fF]$/.test(t)) i++
    }
  }
  return null
}

// chmod with a 777-granting octal mode (777, 0777, 1777, ...: any octal whose
// low 9 bits are 777) in this segment.
function chmodGuard(s) {
  for (let i = 0; i < s.length; i++) {
    if (toolName(s[i]) !== "chmod") continue
    const mode = s.slice(i + 1).find((t) => /^[0-7]*777$/.test(t))
    if (mode) return `Blocked: chmod ${mode} is not permitted. ${CHMOD_REASON}`
  }
  return null
}

// Delete verb with a protected path among its args. Flags are skipped so
// rearrangements (rm -rf, rm -r -f, rm -fr) all match the same.
function deleteVerbGuard(s) {
  for (let i = 0; i < s.length; i++) {
    const verb = toolName(s[i])
    if (!DELETE_VERBS.has(verb)) continue
    for (const arg of s.slice(i + 1)) {
      if (arg.startsWith("-")) continue
      const reason = protectedPathReason(verb, arg)
      if (reason) return reason
    }
  }
  return null
}

// First find in the segment: with a delete action present, any non-option
// token after find that is a protected path denies.
function findGuard(s) {
  const start = s.findIndex((t) => toolName(t) === "find")
  if (start === -1) return null
  const args = s.slice(start + 1)
  const label = findDeleteLabel(args)
  if (!label) return null
  for (const arg of args) {
    if (arg.startsWith("-")) continue
    const reason = protectedPathReason(label, arg)
    if (reason) return reason
  }
  return null
}

// Label of the first delete action, scanning left to right; null when none.
// An exec action counts when a delete verb, by basename (/bin/rm, unlink),
// appears within the window after it.
function findDeleteLabel(args) {
  for (let i = 0; i < args.length; i++) {
    const t = args[i]
    if (t === "-delete" || t === "--delete") return "find -delete"
    if (!FIND_EXEC_ACTIONS.has(t)) continue
    const verb = args
      .slice(i + 1, i + 1 + FIND_EXEC_RM_WINDOW)
      .map(toolName)
      .find((name) => DELETE_VERBS.has(name))
    if (verb) return `find ${t} ${verb}`
  }
  return null
}

// Order decides which reason a multi-violation command reports.
const COMMAND_GUARDS = [sudoGuard, ddGuard, mkfsGuard, kubectlGuard, s3Guard]
const SEGMENT_GUARDS = [gitGuard, ghGuard, chmodGuard, deleteVerbGuard, findGuard]

function firstReason(guards, tokens, env) {
  for (const guard of guards) {
    const reason = guard(tokens, env)
    if (reason) return reason
  }
  return null
}

// One tokenization of the command: `tokens` feed the command-token guards,
// each entry of `segments` the segment guards.
function viewReason({ tokens, segments }, env) {
  const commandReason = firstReason(COMMAND_GUARDS, tokens, env)
  if (commandReason) return commandReason
  for (const s of segments) {
    const reason = firstReason(SEGMENT_GUARDS, s, env)
    if (reason) return reason
  }
  return null
}

// Quote-flattening view: quote/subshell chars become blanks, so a command
// wrapped in a string (bash -c "...", $(...)) tokenizes to its bare words.
function flattenedView(command) {
  return {
    tokens: command.replace(S3_FLATTEN, " ").split(SHELL_WHITESPACE).filter(Boolean),
    segments: command
      .split(SPLIT_SEPS)
      .map((segment) => segment.replace(SEG_FLATTEN, " ").split(SHELL_WHITESPACE).filter(Boolean))
      .filter((s) => s.length > 0),
  }
}

// Quoted view of the command, then of every quoted word holding a blank,
// re-lexed as a nested command (sh -c "aws --query 'a b' s3 rm ..."), down to
// `depth` levels. The flattened view already reads those words as commands, so
// nesting adds no new false-positive class.
function quotedReason(command, env, depth) {
  const view = quotedView(command)
  const reason = viewReason(view, env)
  if (reason || depth === 0) return reason
  for (const word of view.tokens) {
    if (!/[ \t\n]/.test(word)) continue
    const nested = quotedReason(word, env, depth - 1)
    if (nested) return nested
  }
  return null
}

// Quote-honouring view: a quoted span stays inside one word (quotes removed),
// so a blank inside an option value (--query "a b") cannot shift the
// subcommand position. Unquoted separators end a segment; unquoted
// subshell and redirection chars end a word (git push>log is git push). An
// unterminated quote runs to the end.
function quotedView(command) {
  const segments = [[]]
  let word = null
  const endWord = () => {
    if (word !== null) segments.at(-1).push(word)
    word = null
  }
  for (let i = 0; i < command.length; i++) {
    const c = command[i]
    if (c === "'") {
      const close = command.indexOf("'", i + 1)
      const stop = close === -1 ? command.length : close
      word = (word ?? "") + command.slice(i + 1, stop)
      i = stop
    } else if (c === '"') {
      let text = ""
      let j = i + 1
      for (; j < command.length && command[j] !== '"'; j++) {
        if (command[j] === "\\" && j + 1 < command.length) j++
        text += command[j]
      }
      word = (word ?? "") + text
      i = j
    } else if (c === "\\" && i + 1 < command.length) {
      word = (word ?? "") + command[++i]
    } else if (SPLIT_SEPS.test(c)) {
      endWord()
      if (segments.at(-1).length > 0) segments.push([])
    } else if (SHELL_WHITESPACE.test(c) || "`$()<>".includes(c)) {
      endWord()
    } else {
      word = (word ?? "") + c
    }
  }
  endWord()
  const nonEmpty = segments.filter((s) => s.length > 0)
  return { tokens: nonEmpty.flat(), segments: nonEmpty }
}

export function decide(command, env = process.env) {
  if (typeof command !== "string" || command === "") return { deny: false }
  // Collapse backslash-newline continuations BEFORE segmenting, so
  // `gh api -X \<newline> DELETE` can't split a flag from its value across a
  // segment boundary.
  command = command.replace(/\\\n/g, " ").replace(FD_REDIRECT, " ")
  // Either view denying denies: the flattened view sees inside wrapper
  // strings, the quoted view keeps quoted option values whole.
  const reason = viewReason(flattenedView(command), env) ?? quotedReason(command, env, NESTED_COMMAND_DEPTH)
  return reason ? { deny: true, reason } : { deny: false }
}
