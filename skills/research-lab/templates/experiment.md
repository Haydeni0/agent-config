# <EXP-ID>: <title>

<!-- One file per experiment (D5). Brief is written before dispatch and never edited after the
run starts; later changes go in the Entry's Deviations. -->

## Brief

- **Question:** <questions.md row id, or the D/Q entry it serves>
- **Tier:** headline | supporting (D22: headline = answers the study question, is meant for a
  page summary, or costs > 1 GPU-h)
- **depends_on:** [<claim or experiment ids this builds on>] (D24)
- **Goal:** <one sentence>
- **Method:** <what runs, on what data, with which code path; state the frame/units of every
  input changed>
- **Controls:** <random-init / untrained / shuffled / baseline arms; what each rules out>
- **Pre-registered predictions** (one row per prediction):

  | id | prediction | falsified if | metric + split |
  |---|---|---|---|
  | P1 | ... | ... | ... |

- **Cost estimate:** <GPU-h, wall-clock, storage>; within `policy.md` threshold: yes/no
- **Gates:** design review (headline only): <audit file once done>
- **Domain pack:** <packs/<domain>/ pointer>

## Entry

<!-- Written by the worker after the run. A result contradicting a pre-registered prediction
says so FIRST. Every quantitative sentence has a manifest check. -->

- **Prediction outcomes:** P1 held / failed (<one line each, failures first>)
- **Result:** <findings, each sentence citing its manifest check id in brackets, e.g. [c3]>
- **Limits:** <what this does not show; scope of every quantifier>
- **Deviations from the brief:** <what changed and why, or "none">
- **Provenance:** command `<exact command>`; `exp:` commit <SHA>; data <paths + sha256 for
  files > 5 MB>; manifest `<id>_manifest.py`
- **Gate results:** run_checks <n/n>, coverage_scan <clean | waivers>; result audit <file>;
  decision <D id>
