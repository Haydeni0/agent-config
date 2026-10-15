# Kernels pack: failure checklist

Patterns that make a kernel/benchmark result look real when it is not. The critic checks
designs and results against every item; new patterns append to `lab/false-findings.md`
(tagged KERNELS).

- **Timing method**: CUDA events (or profiler kernels) for GPU work, never wall-clock around
  async launches; `torch.cuda.synchronize()` before stopping any host timer. State the
  method in the entry.
- **Warm-up**: exclude warm-up iterations from every reported number; JIT/compile (Warp
  kernel compilation, `torch.compile`, `wp.init`) must complete before timing starts.
- **Sync**: when timing stages separately, each stage's timer must bracket exactly that
  stage with a sync or event pair; beware hidden syncs (`.item()`, `wp.synchronize_device`,
  host transfers) inside a timed region.
- **Input shapes**: production-like, and the config they came from named in the entry. B=1
  for this lab. Edge counts vary with the search seed and point draw: fix the seed, report
  the realised edge count, and re-check timing conclusions at the reported count.
- **Numerical tolerance**: reference = the unmodified code path, same inputs, same dtype.
  State the dtype (bf16 AMP context here), the error metric (max rel err and/or allclose
  threshold), and the threshold before claiming "preserved".
- **Clocks**: boost state drifts and we cannot lock clocks without root. Report
  `nvidia-smi --query-gpu=clocks.sm,clocks.mem,power.draw` before/after; enough reps that
  the speedup exceeds the timing noise floor (report median +- spread); check for thermal
  throttling. Same rep count and interleave for arms being compared.
- **Cache-hot inputs**: repeated identical inputs sit in L2; production streams data. Note
  which regime a number is in; if comparing to production, say so.
- **Launch overhead**: at B=1 with small ops, host launch overhead can dominate; separate
  it (profiler) before claiming a kernel is slow.
- **Allocation effects**: exclude first-iteration allocations from steady-state numbers;
  note peak memory separately from time.
- **Contention**: the node is shared. `nvidia-smi` before and after every run; if GPU 7
  became busy mid-run, void and rerun.
- **Comparison fairness**: baseline and optimised arms must run in the same process state
  (same warm-up, same clocks window, interleaved order), and the baseline must be the
  production code path, not a strawman.
- **Edge count invariance**: an optimisation that changes the neighbour count (e.g.
  different subsample strategy) changes the work, not just the speed; compare at equal
  edge counts or report both.
