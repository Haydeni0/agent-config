# Kernels pack: findings-page template

The lab page (`lab/page.md`) follows the core claim rules (admitted claims only) and this
shape:

```markdown
# <Study title>

<One-paragraph answer to the study question, every number citing a manifest check id.>

## Setup
- Hardware (device name, clocks reported), driver/toolkit versions, dtype, timing method.
- Reference shape: which repo config, its key sizes (points, supernodes, radius, cap,
  widths), realised edge count.

## Stage breakdown
Table: stage | median ms | spread | % of forward. State what is inside each stage.

## Roofline distance (E2)
Table: stage | bound type (BW/FLOP) | % of peak | peak value + source. What the distance
means for each stage (near roofline = do less work; far = implementation slack).

## Optimising the dominant stage (E3)
Speedup table: arm | median ms | speedup vs reference | max rel err vs reference | edge
count | tolerance + dtype. What was changed and why it helps (mechanism, one sentence).

## Limits
What these numbers do not show (single shape, synthetic points, one GPU, unlocked clocks).
```

Figures optional; if present, generated from the cited result JSON (F13).
