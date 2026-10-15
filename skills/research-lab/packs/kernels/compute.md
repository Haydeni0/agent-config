# Kernels pack: compute conventions

Policy limits live in `lab/policy.md`; this says how kernel work uses them.

- Device: `cuda:7` only; every script sets `CUDA_VISIBLE_DEVICES` or an explicit device.
- Before every launch: `nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv`
  and check GPU 7 is idle; also capture `clocks.sm,clocks.mem,power.draw` at start and end of
  each timed run and store them in the result JSON.
- Threads: set `OMP_NUM_THREADS` and `torch.set_num_threads` so total lab CPU threads <= 16.
- Timing: CUDA events for GPU stages, >= 20 timed reps after >= 5 warm-up reps unless the
  brief says otherwise; report median and spread; interleave arms rather than running all
  reps of one arm then the other.
- Profiling: `torch.profiler` (kineto) for stage attribution; export traces to `scratch/`
  and keep < 5 MB (trim or summarise).
- Outputs: scripts and small JSONs under `scratch/` on the lab branch; result JSONs
  referenced by manifests and committed with the `exp:` commit (files > 5 MB by sha256 in
  the manifest).
