# PI profile (research-lab)

Standing rules for every lab this PI runs. Labs copy these into policy.md and record only
deltas. Machine facts (free GPUs, disk, env gates) are probed at startup, not written here.

LAUNCHER: COMMIT_AUTHORISED=1 ~/.local/bin/local-claude
TRUSTED_ROOTS: ~/gitrepos/research-lab-pilot ~/worktrees/research-lpm ~/gitrepos/research-lpm

- TRUSTED_ROOTS: directories whose folder-trust dialog spawn-member may accept for a
  member; anything else stops for the PI.
- Launchers: members and spawned sessions run only the LAUNCHER above (internal GLM
  gateway). Never `claude`, `claudec`, `claudep`, or `herdr agent start --kind claude`: they
  bill the Anthropic API. Subagents never set a `model` override.
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
