# m-pair (wrapper)

This directory is a **wrapper skill**. It is not the real skill.

## Why this exists

`marimo-pair` (a symlink to `~/.claude/vendor/plugins/marimo-pair/skills/marimo-pair`,
backed by the `marimo-team/marimo-pair` git submodule) holds the actual skill
content. We keep the submodule unmodified so it can track upstream cleanly.

This `m-pair` directory is a thin wrapper that delegates to `marimo-pair` for
everything. It exists to give the wrapper a distinct skill name (`/m-pair`) so it
does not collide with the real skill's frontmatter `name: marimo-pair` - typing
`/marimo-pair` hits the real submodule skill directly; `/m-pair` hits this
wrapper. The wrapper also records a local gotcha (the `execute-code.sh`
auth-token handling) that we do not want to push into the upstream submodule.

## Layout

```
~/.claude/skills/
  marimo-pair -> ../vendor/plugins/marimo-pair/skills/marimo-pair   # real skill (submodule)
  m-pair/                                                          # this wrapper
    SKILL.md   # delegates to marimo-pair
    README.md  # this file
```

## To change the real skill

Edit the submodule at `~/.claude/vendor/plugins/marimo-pair/` (separate git
repo). Do not edit it through this wrapper.
