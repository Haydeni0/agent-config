# ML-pxnet pack: failure checklist

Failure checklist for PxNet/lpm ML labs (Hydra/lpm config, pxaircraft data, training and
eval on the subsampled-model-repr stack). The critic checks designs and results against
every item; new patterns append to `lab/false-findings.md` (tagged ML).

## Config / compose

- **Compose outside `lpmrun`**: register the LPM custom Hydra resolvers
  (e.g. `major_version_stem`) before `compose` - importing lpm config directly raises
  otherwise. State in the entry how config was composed.
- **Stale dataset conf**: `conf/dataset/pxaircraft.yaml` points at the v0 spec
  (`undecimated:`-prefixed keys), incompatible with the model conf's unprefixed keys.
  Check the keys the model conf reads actually resolve; override
  `dataset.data_spec_path` per the model yaml's header comment if they do not.
- **Single-process runs**: set `model.training.distributed=null` (and the predict
  equivalent) or the env-var interpolation of WORLD_SIZE raises.

## Data spec / loading

- **Data spec choice**: use `pxaircraft_v5_noval` (loads production samples from S3,
  cwlota endpoint; one sample = 5 h5 files, ~1.32 GB, ~5 s). The v0 and v4_withvol specs
  point at unmaterialized step dirs and fail on this node. If a run must fall back to
  synthetic data, flag it as a deviation in the entry.
- **Synthetic fallback density**: state the synthetic graph's density/size cap in the
  brief and enforce it - the uncapped defaults can OOM a 178 GB B200.
- **S3 prefetch**: concurrent fetch of ~1.3 GB samples at 8 threads is 0.67x sequential;
  use 2-3 threads and cite the measured number when it matters.
- **Split integrity** (ML): verify train/val/test disjointness at the geometry level, not
  by filename; in this spec the val file equals the test file - never select on it.

## Training / eval

- **Supervision resampling** (ML): training targets must be resampled per epoch; a fixed
  cached query-point set trains a decoder to that set. Fixed sets are eval-only.
