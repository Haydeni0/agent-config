# PI profile (research-lab)

Standing rules for every lab this PI runs. Labs copy these into policy.md and record only
deltas. Machine facts (free compute, disk, env gates) are probed at startup, not written here.

TRUSTED_ROOTS: <space-separated directories members may be started in>
BRANCH_PREFIX: <prefix for lab branches, e.g. `yourname/`>

- TRUSTED_ROOTS: directories whose folder-trust dialog spawn-member may accept for a
  member; anything else stops for the PI.
- Compute: <which accelerators/queues labs may use and the check to run before each launch>.
- Data: <read-only data sources and how scripts reach them>.
- Storage: <cache and results caps per lab>.
- Git: commit only through the chained gate `printenv COMMIT_AUTHORISED && git commit ...`;
  push only via `printenv PUSH_AUTHORISED && git push ...`. One provenance commit per
  accepted experiment.
- Publishing: nothing outward (Notion, Slack, PRs) without a PI message.
- Interrupts: D16 only. Report at the deadline with the page path. Status lives in files.
- Style: terse. No em dashes.

## Staffing

| role | launcher | model | effort |
|---|---|---|---|
| default | <shell command that starts an agent session, e.g. `claude`> | | |
| worker | | | |
| author | | | |

The command each member runs is `<launcher> --model <model> --effort <effort>`
from its role's row; empty cells fall back to the `default` row, and an empty model or
effort is left to the launcher. Members run only these commands, never another binary or
a harness default; subagents never set a `model` override. Note here any launcher that
costs money, so labs avoid it unless the PI says otherwise.

## Resources (cross-lab facts)

Known-good facts labs found (data paths, launch recipes, environment quirks), each with how
it was verified, the lab and the date. The overseer appends at lab finish and corrects wrong
entries. Labs read this at startup before searching.
