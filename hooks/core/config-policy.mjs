import path from "node:path"

const WRITE_OPS = /\b(tee|sed|dd|cp|install|rsync|mv|rm|rmdir|shred|unlink)\b/
const SED_INPLACE = /(^|\s)-i\w*\b|--in-place\b/
// write-redirect operator capturing its target file token (excludes fd-to-fd like
// 2>&1 and input redirects <). Applied after stripContexts + ~/$HOME expand, so
// prose ">" is already gone. ponytail: target-aware - a read of the dir with stderr
// to /dev/null (or any redirect whose target isn't the dir) is allowed; only a
// redirect whose resolved target is the dir blocks. Relative targets resolve
// against process.cwd(); protected dirs are absolute, so a bareword target only
// hits when cwd is in the dir (rare).
const WRITE_REDIR = /(?:^|\s)(?:&>>?|\d*>>?\|?)(?!&\d)\s*(\S+)/g

// Strip quoted strings and [[ ]]/(( )) so prose ">" ("->", "=>", "$a > $b")
// doesn't look like a redirect. ponytail: naive - add a lexer if it bites.
function stripContexts(c) {
  return c
    .replace(/"([^"\\]|\\.)*"/g, " ")
    .replace(/'[^']*'/g, " ")
    .replace(/\[\[[\s\S]*?\]\]/g, " ")
    .replace(/\(\([\s\S]*?\)\)/g, " ")
}

export function bashWritesTo(command, dir, home) {
  // Collapse backslash-newline continuations before segmenting, so
  // `echo x > \<newline> dir/config.json` can't split a redirect from its
  // target across the segment split.
  const c = stripContexts(command.replace(/\\\n/g, " ")).replace(/~/g, home).replace(/\$HOME\b/g, home)
  const dirRe = new RegExp(dir.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(?:[/\\\\]|$)")
  if (!dirRe.test(c)) return false
  for (const seg of c.split(/[\n\r]+|&&|\|\||;|(?<!>)\|(?![&|])/)) {
    // a redirect only counts if its resolved target is the dir (not /dev/null etc.)
    WRITE_REDIR.lastIndex = 0
    let m = WRITE_REDIR.exec(seg)
    while (m !== null) {
      const target = path.resolve(m[1])
      if (target === dir || target.startsWith(dir + path.sep)) return true
      m = WRITE_REDIR.exec(seg)
    }
    const w = seg.trim().replace(/^sudo\s+/, "").replace(/^(?:\w+=\S+\s+)+/, "").match(/^(\w[\w-]*)/)
    if (w && WRITE_OPS.test(w[1])) {
      if (w[1] === "sed" && !SED_INPLACE.test(seg)) continue
      return true
    }
  }
  return false
}
