---
name: kubectl
description: Use when running kubectl commands against a cluster - read-only only (get, logs, describe, top, rollout status); exec is read-only-inspect only.
---

# Using kubectl

Default to **read-only** kubectl. Inspect cluster state; do not mutate it.

## Read-only (allowed)

```bash
kubectl get pods
kubectl get pods -n kube-system
kubectl logs <pod>
kubectl logs -f <pod> -c <container>
kubectl describe <resource>
kubectl top pods
kubectl rollout status deployment <name>   # observes a rollout, does not change it
```

## Mutation verbs are hard-blocked

The shared command policy (`hooks/core/command-policy.mjs`, behind every harness's command hook) hard-denies all mutation verbs. Do not attempt them - they will fail. If the user needs one, tell them to run it themselves outside Claude:

- `delete`, `deletecollection` - remove resources
- `drain`, `cordon`, `uncordon`, `taint` - node scheduling changes
- `edit`, `apply`, `create`, `patch`, `replace` - create or modify resources
- `scale`, `set`, `expose`, `autoscale`, `run` - change workload config
- `label`, `annotate`, `cp` - modify metadata or copy files in/out of pods
- `rollout restart`, `rollout undo`, `rollout pause`, `rollout resume` - mutate rollout state

`k` (the kubectl alias) is covered by the same guard.

## exec - inspect only

`kubectl exec` is allowed by the guard, but treat the pod as read-only:

```bash
kubectl exec <pod> -- ls /app
kubectl exec <pod> -- cat /etc/hosts
kubectl exec <pod> -- env
```

**Only inspect - do not modify the pod's state.** No `rm`, `curl`, `apt install`, `pip`, writing files, or anything that changes the running pod. If the user needs to modify pod state via exec, tell them to run it themselves outside Claude.
