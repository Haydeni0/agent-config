# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
# ///
"""Lab checker for research-lab evidence manifests: manifest checks, Entry
coverage scan, and citation cross-index.

Domain-neutral core rules (pilot F24):

- ``value``: the quote's closest number matches the computed value - sign inside
  capture, exact when ``rounding=`` is set (a relative tolerance let a mutated
  value through in the pilot), relative tolerance ``tol`` otherwise.
- ``range``: the quote's range endpoints match the computed domain's min/max.
- ``quantifier``: every element of the computed domain satisfies the predicate
  against ``bound`` (``all/each/only/no/...`` prose).
- split attribution: a split named in the quote must be filtered by in ``expr``.
- unit agreement (pilot R5): a quote stating "%" is checked against the JSON
  value scaled x100 for value/range kinds - store shares/fractions in the JSON
  and quote them as percentages. Quantifier bounds are the quoted percent
  divided by 100 in the Check field and scaled back before comparison.

Domain ``kind`` aliases: each domain pack lists its kinds (e.g.
``packs/kernels/checks.md``); the ``PACK_KIND_ALIASES`` table below is the
explicit per-pack mapping onto the core semantics - add a row when a new pack
defines kinds, no other wiring.

``kind="novelty"`` (D27) is carried, not evaluated: the data file (a
literature-spike artifact) must exist, and the quote is cross-indexed like
every other check.

Cross-index, both directions over the Entry section:
- every ``[c-*]`` id cited in the Entry must resolve to a manifest Check id;
- every manifest Check quote must appear verbatim in the Entry.

Claim-ledger fields (``status``, ``falsification``, ``forbidden``,
``depends_on``, ``audit_note``) are carried, not evaluated here; status changes
only at the overseer's Decision step.

Usage:
    uv run --script lab_checker.py <manifest.py> <experiment.md>

Exits non-zero on any check failure, cross-index failure, or uncovered
number-bearing Entry sentence (each uncovered sentence must be waived with a
reason or given its own check before the result audit is launched).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

_NUM = r"[+-]?\d+(?:\.\d+)?"
RANGE_RE = re.compile(rf"({_NUM})\s*(?:to|-|–|—)\s*({_NUM})")
SINGLE_RE = re.compile(rf"{_NUM}")
QUANT_RE = re.compile(
    r"\b(all|every|each|only|no|at most|at least|under|below|above|never|always)\b",
    re.IGNORECASE,
)
# splits named in lab prose: dtype arms plus the pilot's original tokens
SPLIT_TOKENS = ("test", "train", "pooled", "bf16", "fp32")

# domain-pack kind aliases -> core semantics; sources: packs/<pack>/checks.md
PACK_KIND_ALIASES: dict[str, dict[str, str]] = {
    "kernels": {
        "timing": "value",
        "speedup": "value",
        "shapes": "value",
        "hardware": "value",
        "roofline": "value",
        "correctness_tolerance": "range",
    },
}
KIND_ALIASES = {k: v for aliases in PACK_KIND_ALIASES.values() for k, v in aliases.items()}
CORE_KINDS = {"value", "range", "quantifier", "novelty"}


@dataclass
class Check:
    """One prose claim + the data computation it must match."""

    id: str
    quote: str
    data: str
    expr: str
    kind: str = "value"  # core kind or a pack alias
    domain: str = ""
    bound: float = 0.0
    predicate: str = ""
    unit: str = ""
    tol: float = 0.02
    rounding: int | None = None  # exact match after rounding to N dp
    # claim-ledger fields (D20, D24); carried, not evaluated
    status: str = ""  # set only at the Decision step
    falsification: str = ""
    forbidden: str = ""
    depends_on: list[str] = field(default_factory=list)
    audit_note: str = ""

    def core_kind(self) -> str:
        if self.kind in KIND_ALIASES:
            return KIND_ALIASES[self.kind]
        if self.kind in CORE_KINDS:
            return self.kind
        raise ValueError(f"unknown kind {self.kind!r}")


@dataclass
class Failure:
    check_id: str
    rule: str
    detail: str


def _load(data_path: str) -> Any:
    import json

    p = Path(data_path)
    if p.suffix == ".json":
        return json.loads(p.read_text())
    if p.suffix in {".npz", ".npy"}:
        return dict(np.load(p, allow_pickle=True))
    raise ValueError(f"unsupported data file {data_path}")


def _extract_quote_numbers(quote: str) -> dict[str, Any]:
    rng = RANGE_RE.search(quote)
    if rng:
        lo, hi = float(rng.group(1)), float(rng.group(2))
        lo, hi = min(lo, hi), max(lo, hi)
    else:
        lo = hi = None
    singles = [(m.start(), m.group(0)) for m in SINGLE_RE.finditer(quote)]
    quants = [m.group(0).lower() for m in QUANT_RE.finditer(quote)]
    splits = [t for t in SPLIT_TOKENS if re.search(rf"\b{t}\b", quote, re.IGNORECASE)]
    return {"lo": lo, "hi": hi, "singles": singles, "quantifiers": quants, "splits": splits}


def _to_percent(quote: str, value: float) -> float:
    return value * 100.0 if "%" in quote else value


def _value_matches(prose: float, target: float, check: Check) -> str | None:
    """Exact-rounding or relative-tolerance value comparison; None = match."""
    if check.rounding is not None:
        if round(target, check.rounding) != round(prose, check.rounding):
            return f"rounding {check.rounding}dp: prose {prose:g} vs computed {target:.6g}"
        return None
    if abs(prose - target) > max(check.tol * max(abs(target), abs(prose)), 1e-12):
        return f"prose {prose:g} vs computed {target:.6g}"
    return None


def run_check(check: Check, data: Any) -> Failure | None:
    core = check.core_kind()

    if core == "novelty":
        # D27: the data file is a literature-spike artifact, not numbers to evaluate
        if not Path(check.data).is_file():
            return Failure(check.id, "novelty", f"data file not found: {check.data}")
        return None

    quoted = _extract_quote_numbers(check.quote)

    # R2 split-attribution: quote-named splits must appear in the expr filter.
    for s in quoted["splits"]:
        if s not in check.expr:
            return Failure(
                check.id,
                "R2 split-attribution",
                f"quote names split '{s}' but expr does not filter by it: {check.expr}",
            )

    value = eval(check.expr, {"np": np, "d": data, "_len": len})  # noqa: S307 - trusted lab code
    arr = np.asarray(value, dtype=float).ravel()

    if core == "value":
        if arr.size != 1:
            return Failure(check.id, "value", f"expr returned {arr.size} values, expected 1")
        target = _to_percent(check.quote, float(arr[0]))
        if not quoted["singles"]:
            return Failure(check.id, "value", "no number found in quote to check against")
        cands = [(abs(float(s) - abs(target)), float(s)) for _, s in quoted["singles"]]
        prose = min(cands)[1]
        if abs(prose) < 1e-12 or abs(target) < 1e-12:
            sign_ok = (prose == 0) == (target == 0)
        else:
            sign_ok = (prose > 0) == (target > 0)
        if not sign_ok:
            return Failure(
                check.id,
                "R1 sign",
                f"prose {prose:+g} vs computed {target:+g} ({check.data}::{check.expr})",
            )
        mismatch = _value_matches(prose, target, check)
        if mismatch:
            unit = "%" if "%" in check.quote else "raw"
            return Failure(check.id, "R5 value/unit", f"{mismatch} (unit={unit})")

    elif core == "range":
        if arr.size < 2:
            return Failure(check.id, "R4 range", "range check needs a multi-value domain")
        lo_c = _to_percent(check.quote, float(arr.min()))
        hi_c = _to_percent(check.quote, float(arr.max()))
        if quoted["lo"] is None:
            return Failure(check.id, "R4 range", "no range found in quote")
        if check.rounding is not None:
            if round(lo_c, check.rounding) != round(quoted["lo"], check.rounding) or round(
                hi_c, check.rounding
            ) != round(quoted["hi"], check.rounding):
                return Failure(
                    check.id,
                    "R4 range-endpoints",
                    f"rounding {check.rounding}dp: prose [{quoted['lo']:g}, {quoted['hi']:g}] "
                    f"vs domain min/max [{lo_c:.4g}, {hi_c:.4g}] over {check.domain or 'domain'}",
                )
        else:
            ok = abs(quoted["lo"] - lo_c) <= check.tol * max(abs(lo_c), 1e-9) and abs(
                quoted["hi"] - hi_c
            ) <= check.tol * max(abs(hi_c), 1e-9)
            if not ok:
                return Failure(
                    check.id,
                    "R4 range-endpoints",
                    f"prose [{quoted['lo']:g}, {quoted['hi']:g}] vs domain min/max "
                    f"[{lo_c:.4g}, {hi_c:.4g}] over {check.domain or 'domain'}",
                )

    elif core == "quantifier":
        if check.predicate not in {"ge", "le"}:
            return Failure(check.id, "R3 quantifier", f"bad predicate {check.predicate!r}")
        bound = _to_percent(check.quote, check.bound)
        viol = (arr < bound) if check.predicate == "ge" else (arr > bound)
        if bool(viol.any()):
            worst = float(arr[viol][np.argmax(np.abs(arr[viol] - bound))])
            return Failure(
                check.id,
                "R3 quantifier",
                f"prose quantifier over {check.domain or 'domain'} violated: worst "
                f"{worst:.4g} vs bound {bound:g} ({check.data}::{check.expr})",
            )
        extreme = float(arr.min() if check.predicate == "ge" else arr.max())
        if bound != 0 and abs(bound - extreme) > abs(extreme) * 2:
            print(f"WARN {check.id}: bound {bound:g} is >2x slack vs extreme {extreme:.4g}")
    return None


def run_checks(checks: list[Check], quiet: bool = False) -> list[Failure]:
    failures = []
    for c in checks:
        if c.core_kind() == "novelty":
            data = None
        else:
            data = _load(c.data)
        f = run_check(c, data)
        if f is not None:
            failures.append(f)
            if not quiet:
                print(f"FAIL {f.check_id} [{f.rule}]: {f.detail}")
        elif not quiet:
            print(f"PASS {c.id}")
    return failures


_NUM_SENT_RE = re.compile(
    r"[^.\n]*(?:\d+\.\d+|\b\d+%|\b\d+\s*(?:ms|MHz|GiB|GB|MB)\b)[^.\n]*\.", re.MULTILINE
)

_CITATION_RE = re.compile(r"\[(c-[A-Za-z0-9_-]+)\]")


def _read_section(md_path: Path, section: str) -> tuple[str, int]:
    """(section text incl. its heading, 0-based line index of the heading)."""
    text = md_path.read_text()
    m = re.search(rf"^{re.escape(section)}.*?(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        raise ValueError(f"section {section!r} not found in {md_path}")
    return m.group(0), text[: m.start()].count("\n")


def coverage_scan(md_path: Path, quotes: list[str], section: str | None = None) -> list[str]:
    """Sentences bearing numbers that no manifest quote covers. Heuristic coverage gate.

    Args:
        md_path: the experiment file (brief + entry in one file).
        quotes: manifest quotes.
        section: if set (e.g. "## Entry"), scan only that section.
    """
    if section:
        text, _ = _read_section(md_path, section)
    else:
        text = md_path.read_text()
    # raw-number tables are exempt from checks (verifier-spec F24: "tables of raw
    # numbers do not need checks - prose does"), so drop table lines before
    # sentence extraction (row-internal decimals would otherwise split into
    # fragments that look like uncovered sentences).
    text = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("|"))
    sentences = [m.group(0).strip() for m in _NUM_SENT_RE.finditer(text)]
    unregistered = []
    for s in sentences:
        if not any(q[:60] in s or s[:60] in q for q in quotes):
            unregistered.append(s)
    return unregistered


def cross_index(checks: list[Check], md_path: Path, section: str = "## Entry") -> list[Failure]:
    """Both directions of the citation cross-index over one section.

    - every ``[c-*]`` id cited in the section resolves to a manifest Check id;
    - every manifest Check quote appears verbatim in the section.
    Citation failures name the cited id and the Entry line; quote failures name
    the Check id and the absent quote.
    """
    text, first_line = _read_section(md_path, section)
    ids = {c.id for c in checks}
    failures = []
    for i, line in enumerate(text.splitlines()):
        for m in _CITATION_RE.finditer(line):
            if m.group(1) not in ids:
                failures.append(
                    Failure(
                        m.group(1),
                        "cross-index citation",
                        f"Entry line {first_line + i + 1}: {line.strip()[:120]}",
                    )
                )
    for c in checks:
        if c.quote and c.quote not in text:
            failures.append(
                Failure(
                    c.id,
                    "cross-index quote",
                    f"quote not found verbatim in the Entry: {c.quote[:80]!r}",
                )
            )
    return failures


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    manifest_path, experiment_path = sys.argv[1], sys.argv[2]
    # manifests import their Check: make this file importable as lab_checker
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    namespace: dict[str, Any] = {"Check": Check, "CHECKS": [], "__file__": manifest_path}
    exec(Path(manifest_path).read_text(), namespace)  # noqa: S102 - trusted lab code
    checks: list[Check] = namespace.get("CHECKS", [])
    failures = run_checks(checks)
    md = Path(experiment_path)
    try:
        xfailures = cross_index(checks, md)
        unregistered = coverage_scan(md, [c.quote for c in checks], section="## Entry")
    except ValueError as e:
        print(f"COVERAGE-ERROR: {e}")
        return 1
    print(f"checks: {len(checks) - len(failures)}/{len(checks)} pass")
    for f in xfailures:
        print(f"FAIL {f.check_id} [{f.rule}]: {f.detail}")
    for s in unregistered:
        print(f"UNCOVERED: {s}")
    print(f"coverage: {'clean' if not unregistered else f'{len(unregistered)} uncovered sentence(s)'}")
    return 1 if (failures or xfailures or unregistered) else 0


if __name__ == "__main__":
    sys.exit(main())
