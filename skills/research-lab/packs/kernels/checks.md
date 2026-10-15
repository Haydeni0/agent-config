# Kernels pack: manifest check types

Check `kind` values the kernels domain adds to the core set (value, range, quantifier):

| kind | checks | example expr |
|---|---|---|
| `timing` | median and spread of a stage time, method stated | `[d['radius_search_ms']['median']]` with `rounding=2` |
| `speedup` | ratio of baseline vs optimised at stated shape, same edge count | `[d['e3']['speedup']...]` |
| `correctness_tolerance` | max rel err vs reference within the stated tolerance, dtype stated | `[d['max_rel_err']]` with `range` `[0, tol]` |
| `shapes` | input/output shapes and realised edge count match the brief's shape | `[d['edge_count']]` |
| `hardware` | device name, SM/mem clocks, power captured in the result JSON | `[d['gpu_name']]` |
| `roofline` | % of peak BW or FLOPs at the measured point, peak value's source named | `[d['pct_peak_bw']...]` |

Prose numbers that are rounded are checked by exact rounding (core rule, template
manifest.md). Peak-spec numbers (e.g. B200 HBM bandwidth) must cite their source artifact
in the manifest (`data` field) - vendor datasheet or measured copy-benchmark output, not
memory.
