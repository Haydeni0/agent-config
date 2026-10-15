# Kernels pack: literature sources

- Vendor specs (roofline peaks): NVIDIA B200 datasheet / HGX docs - HBM3e bandwidth and
  dense bf16 FLOP/s. Cite the fetched page or a saved copy under `lit/`; never from memory
  (D27-adjacent: peak numbers are claims too).
- Measured peaks beat datasheet peaks for roofline distance: a quick triad/copy benchmark
  and a matmul sweep on cuda:7, saved as JSON, are the preferred `data` artifacts for
  peak-BW / peak-FLOP manifest checks.
- arXiv / papers only if a mechanism needs prior art; no novelty claims are planned in this
  study, so no novelty checks are expected.
