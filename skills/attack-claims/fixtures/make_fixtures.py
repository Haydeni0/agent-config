# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///
"""Generate the attack-claims data fixtures (F1, F2, F8) with planted, asserted properties."""

import random
import statistics
from pathlib import Path

import typer

SEED = 20261014
ROWS = 2000
CONFOUNDED_NOISE_SD = 0.7  # A and B each = Z + noise: corr(A, B) ~ 0.67, zero once Z is regressed out
DIRECT_EFFECT = 0.8
STRONG_CORRELATION = 0.5
NEGLIGIBLE_PARTIAL = 0.1
F8_ROWS = 200_000  # ~2.2 MB, well over the 1 MB per-download cap F8's run sets
F8_TARGET_ID = 190_000  # past the first 1 MB, so a truncated fetch cannot reach it


def residuals(ys: list[float], xs: list[float]) -> list[float]:
    slope, intercept = statistics.linear_regression(xs, ys)
    return [y - (slope * x + intercept) for x, y in zip(xs, ys)]


def partial_correlation(a: list[float], b: list[float], z: list[float]) -> float:
    return statistics.correlation(residuals(a, z), residuals(b, z))


def write_csv(path: Path, header: str, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n" + "\n".join(",".join(f"{v:.6f}" if isinstance(v, float) else str(v) for v in row) for row in rows) + "\n")


def make_f1(out: Path, rng: random.Random) -> None:
    z = [rng.gauss(0, 1) for _ in range(ROWS)]
    a = [zi + rng.gauss(0, CONFOUNDED_NOISE_SD) for zi in z]
    b = [zi + rng.gauss(0, CONFOUNDED_NOISE_SD) for zi in z]
    raw, partial = statistics.correlation(a, b), partial_correlation(a, b, z)
    if raw < STRONG_CORRELATION or abs(partial) > NEGLIGIBLE_PARTIAL:
        raise SystemExit(f"F1 property failed: corr(A,B)={raw:.3f} partial|Z={partial:.3f}")
    write_csv(out / "f1.csv", "A,B,Z", list(zip(a, b, z)))
    typer.echo(f"F1 corr(A,B)={raw:.3f} partial|Z={partial:.3f}")


def make_f2(out: Path, rng: random.Random) -> None:
    a = [rng.gauss(0, 1) for _ in range(ROWS)]
    z = [rng.gauss(0, 1) for _ in range(ROWS)]
    b = [DIRECT_EFFECT * ai + rng.gauss(0, 0.5) for ai in a]
    raw, partial = statistics.correlation(a, b), partial_correlation(a, b, z)
    if raw < STRONG_CORRELATION or partial < STRONG_CORRELATION:
        raise SystemExit(f"F2 property failed: corr(A,B)={raw:.3f} partial|Z={partial:.3f}")
    write_csv(out / "f2.csv", "A,B,Z", list(zip(a, b, z)))
    typer.echo(f"F2 corr(A,B)={raw:.3f} partial|Z={partial:.3f}")


def make_f8(out: Path, rng: random.Random) -> None:
    # The target row's value is a serve-time secret: SystemRandom, not the committed
    # seed, so re-running the generator never reproduces the served file's value and
    # no committed artifact names it. Otherwise a T1 attacker greps the repo for the
    # answer and F8 refutes without any download.
    sys_rng = random.SystemRandom()
    target = sys_rng.randint(0, 9999)
    if target == 4242:
        raise SystemExit("F8 property failed: target row drew the claimed value 4242")
    rows = [(i, target if i == F8_TARGET_ID else rng.randint(0, 9999)) for i in range(F8_ROWS)]
    path = out / "f8" / "big.csv"
    write_csv(path, "id,value", rows)
    size = path.stat().st_size
    if size <= 1_000_000:
        raise SystemExit(f"F8 property failed: big.csv is {size} bytes, not over the 1 MB test cap")
    typer.echo(f"F8 big.csv {size} bytes, row {F8_TARGET_ID} value {target} (serve-time secret - record in the run deviation log only, never commit)")


def main(out_dir: Path) -> None:
    rng = random.Random(SEED)
    make_f1(out_dir, rng)
    make_f2(out_dir, rng)
    make_f8(out_dir, rng)


if __name__ == "__main__":
    typer.run(main)
