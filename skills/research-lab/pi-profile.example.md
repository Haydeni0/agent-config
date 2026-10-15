# PI profile (research-lab)

Standing rules for every lab this PI runs. Labs copy these into policy.md and record only
deltas. Machine facts (free GPUs, disk, env gates) are probed at startup, not written here.

LAUNCHER: <shell command that starts a member's agent session, e.g. `claude`>
TRUSTED_ROOTS: <space-separated directories members may be started in>

- LAUNCHER: the default command for every member and spawned session. Override it per role
  with `LAUNCHER.<role>: <command>` (roles: worker, author), e.g. an author on a
  vision-capable model. Members run only these launchers, never another binary or a harness
  default; subagents never set a `model` override. Note here any launcher that costs money,
  so labs avoid it unless the PI says otherwise.
- TRUSTED_ROOTS: directories whose folder-trust dialog spawn-member may accept for a
  member; anything else stops for the PI.
- GPUs: use a GPU only if `nvidia-smi` shows it free immediately before launch. SLURM QoS
  preemptible-mid allowed for resumable jobs. OMP threads 8-16 per process.
- Data: S3 bucket `training-data-04a` is read-only. Scripts that read S3 run with
  `AWS_ENDPOINT_URL_S3=http://cwlota.com MLFLOW_DISABLE_AGENT_HINT=1 uv run python ...`.
- Storage: caches soft 20 GB, hard 50 GB per lab unless the lab policy says otherwise.
- Git: commit only through the chained gate `printenv COMMIT_AUTHORISED && git commit ...`;
  push only via `printenv PUSH_AUTHORISED && git push ...`. No Co-Authored-By trailers.
  Branches prefixed `hayden/`. One provenance commit per accepted experiment.
- Publishing: nothing outward (Notion, Slack, PRs) without a PI message.
- Interrupts: D16 only. Report at the deadline with the page path. Status lives in files.
- Style: terse. No em dashes.

## Resources (cross-lab facts)

Known-good facts labs found (data paths, launch recipes, environment quirks), each with how
it was verified, the lab and the date. The overseer appends at lab finish and corrects wrong
entries. Labs read this at startup before searching.
