# Data-loading benchmark checklist

Failure modes for prefetch/throughput runs. Check the entry against every line before
reporting. Adapted from T3 with its D5 correction (5 files per sample, ~1.32 GB).

- Warmup excluded: first-sample times (S3 client handshake, first h5 open) reported separately,
  never mixed into medians.
- Fetch != decode: bytes-on-wire timed separately from h5 deserialization; say which
  instrument measured which number.
- Shared node: log `uptime`/load at each run start; medians + IQR over repeats, never a single
  sample as "the" number.
- Threading model named: threads vs processes is a different claim under the GIL; every rate
  states which.
- Thread caps enforced: every arm's total workers (prefetch pool + OMP + torch + KDTree) <= 8,
  verified in the process env actually used - a 8-thread pool plus 8 OMP threads is a 16-way
  claim on an 8-way cap.
- Same sample ids in every arm: comparison must not be sample-mix confounded.
- File layout accounted: per sample = 5 h5 files (~1.32 GB) with volume streams ON; state
  which stages the rate covers (fetch-only is not end-to-end).
- Process pool arms: count worker spawn/pickle cost separately from steady-state; a rate that
  includes pool startup is not comparable to a thread-pool rate that does not.
- S3 hygiene: spec downloaded to /tmp before grepping (SIGPIPE truncation trap); never
  `--recursive`; bucket read-only.
- Replications: re-implement the bench; never reuse the replicated lab's timing code.
- **Process pools and S3**: workers that touch the S3 client use the spawn context plus a per-worker client initializer; fork with a parent boto3 client dies with BrokenProcessPool and no child traceback.
