# Lab policy

<!-- Written with the PI at lab startup (D23). Members read it from the brief's pointer; the
overseer checks every brief against it and asks the PI only above the thresholds here. -->

## Time box

- Deadline: <ISO datetime from `date`, or none>
- Gates: <by-time checkpoints for headline experiments, marked `by`>

## Compute

- Allowed: <GPUs / queues / clusters>, conditions: <e.g. free on the profile's compute check immediately
  before launch; preemptible queues only for resumable jobs>
- Thread caps: <e.g. OMP_NUM_THREADS 8-16>
- Ask the PI above: <N GPU-h per experiment> (no fixed default; each brief states its
  estimate)

## Storage

- Caches: soft <X GB>, hard <Y GB>; locations: <paths>

## Data

- Read-only sources: <buckets / paths>
- Writable: <scratch paths>

## Permissions

- Commit: yes, on <research branch / repo>; provenance commits only via `scripts/lab_commit.py` (D8: hooks run on code before the run; the commit holds the bytes that ran)
  and `git add -f` for gitignored result dirs (e.g. `scratch/`)
- Push: <yes/no>
- Shared publishing (pages, docs): <who may publish where; PI message required?>

## People

- PI: <name>; interrupt only per D16 (scope, reversing a PI decision, irreversible or
  outward actions, spend above threshold, dead ends)
