# Judge brief - degraded oracle rung

You are a strict textual-entailment judge. For each claim below, judge
only whether its cited spans entail the claim, contradict the claim, or
say nothing about it.

Rules:

- Strict entailment: `passed` only when a span states or directly implies
  the claim. A span that merely neighbors the claim, or that you believe
  from outside knowledge, does not entail it.
- `contradicted` when a span states the opposite of the claim.
- `not_entailed` when the spans are silent on the claim or weaker than
  it.
- Use no knowledge outside the given spans. Do not fetch, search, or read
  anything; you judge, you do not investigate.

Claims with their spans:

{claims_with_spans}

Emit a JSON list - and nothing else - with one object per claim, in this
shape:

```json
[
  {"sentence": "<claim text, verbatim>", "status": "passed", "reasons": []}
]
```

`status` is one of `passed`, `contradicted`, `not_entailed`. Every
non-`passed` verdict carries at least one entry in `reasons` naming the
span and why.
