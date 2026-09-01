"""Re-measure the Stage 1 bootstrap α and the detection floor on futures.

    python -m futuresres.integrity.calibration --part alpha
    python -m futuresres.integrity.calibration --part floor

BOTH NUMBERS THE PIPELINE CURRENTLY USES WERE MEASURED ON BITCOIN. CLAUDE_FUTURES.md §4
flags them as inherited and wrong until re-measured; this is that measurement. They are
done PER PRODUCT because the tails differ far more than the catalog predicted — MNQ is
γ₄ = 115.1 at one minute and MGC is 226.5, so a single calibration would be wrong for at
least one of them.

──────────────────────────────────────────────────────────────────────────────
A. THE α-TO-COVERAGE MAPPING

A percentile bootstrap interval UNDER-COVERS on heavy tails: ask for 95% and you get less.
The crypto project measured how much less and inverted it, producing a nominal α tighter
than 0.05 that delivers a true 95%. The mapping is indexed by the number of BLOCKS, not
bars, because that is the effective sample size of a block bootstrap.

The statistic measured here is the one Stage 1 actually computes — the signed shift from
`evaluate_signed_signal`, block-bootstrapped the same way, on REAL futures returns. Not a
proxy, and not simulated returns: the whole point is to capture the true tail and the true
serial dependence, and a GARCH fit would capture only what was fitted.

Under the null the signal is independent of returns, so the true signed shift is zero and
coverage is the fraction of intervals containing zero. Sampling a CONTIGUOUS window of real
returns per replication preserves both the tail and the clustering.

──────────────────────────────────────────────────────────────────────────────
B. THE DETECTION FLOOR

Same design as crypto: inject a known edge, sweep its size, find the smallest that gets
promoted end-to-end at >= 80%. Below that floor a null carries no information because
nothing would have been found either way.

Effect size is in units of ONE BAR'S volatility at the horizon being measured, so floors
are comparable across horizons and against crypto's 0.1592x.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Sequence

import numpy as np
import polars as pl

from futuresres.reporting.kurtosis import horizon_returns
from futuresres.signals.search import run_pipeline
from futuresres.signals.stage1 import DEFAULT_BLOCK

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
REPORTS_DIR: Final[Path] = ROOT / "reports"
REPORT: Final[Path] = ROOT / "reports" / "calibration.md"
CACHE: Final[Path] = ROOT / "reports" / "calibration_cache.json"

PRODUCTS: Final[tuple[str, ...]] = ("MNQ", "MGC")
HORIZONS: Final[tuple[int, ...]] = (1, 60, 180)

#: Block counts to calibrate at. Matches the crypto ladder so the two are comparable.
BLOCK_COUNTS: Final[tuple[int, ...]] = (50, 100, 250, 500, 1000)

#: Nominal alphas evaluated per replication. One bootstrap serves all of them, which is
#: what makes 8,000 replications per cell affordable.
ALPHA_GRID: Final[np.ndarray] = np.array(
    [0.010, 0.015, 0.020, 0.025, 0.030, 0.035, 0.040, 0.045, 0.050, 0.060, 0.070]
)
TARGET_COVERAGE: Final[float] = 0.95

#: Fraction of bars carrying a signal in the calibration null — a realistic Stage 1 rate.
SIGNAL_RATE: Final[float] = 0.01

POWER_TARGET: Final[float] = 0.80



# ══════════════════════════════════════════════════════════════════════════════
# checkpointing
# ══════════════════════════════════════════════════════════════════════════════

CKPT_ALPHA: Final[Path] = REPORTS_DIR / "calibration_alpha.ckpt.jsonl"
CKPT_FLOOR: Final[Path] = REPORTS_DIR / "calibration_floor.ckpt.jsonl"


class Checkpoint:
    """Append-only per-cell results, so an interrupted run resumes rather than restarts.

    ONE CELL IS ONE LINE, written and flushed as soon as it completes. A teardown costs the
    cell in flight and nothing else. Resuming is only sound because `cell_seed` is stable
    across processes — a resumed cell draws exactly the numbers the original would have, so
    a run assembled from three interrupted attempts equals one uninterrupted run.
    """

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self.done: dict[str, dict] = {}
        if enabled and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.done[rec["key"]] = rec["value"]

    @staticmethod
    def key(*parts: object) -> str:
        return "|".join(str(p) for p in parts)

    def get(self, key: str):
        return self.done.get(key) if self.enabled else None

    def put(self, key: str, value) -> None:
        if not self.enabled:
            return
        self.done[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": key, "value": value}) + "\n")
            fh.flush()


# ══════════════════════════════════════════════════════════════════════════════
# real return pools
# ══════════════════════════════════════════════════════════════════════════════


def return_pool(product: str, horizon: int) -> np.ndarray:
    """Real h-minute returns, within one contract and one session."""
    bars = pl.read_parquet(CONTINUOUS / f"{product}.parquet")
    r = horizon_returns(bars, horizon)
    return r[np.isfinite(r)]



def cell_seed(seed: int, *parts: object) -> int:
    """A stable per-cell seed. CLAUDE_FUTURES.md §10: "seed all RNG; log seeds".

    NOT `hash()`. Python randomises string hashing per process, so `abs(hash(("MNQ", 1, 50)))`
    returns a different value in every interpreter — measured 1,576,282,033 in one process
    and 976,449,620 in the next. Seeding a calibration that way makes it unreproducible from
    its own recorded seed, which for a number that gates Stage 1 is the difference between a
    measurement and an anecdote.

    SHA-256 of the joined key is stable across processes, machines and Python versions, and
    each cell is seeded from its own identity so a resumed or reordered run reproduces
    exactly what an uninterrupted one would have produced.
    """
    key = "|".join(str(p) for p in (seed, *parts)).encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big") % (2 ** 32)


# ══════════════════════════════════════════════════════════════════════════════
# A. coverage
# ══════════════════════════════════════════════════════════════════════════════


def _block_bootstrap_signed(d: np.ndarray, f: np.ndarray, n_boot: int, block: int,
                            rng: np.random.Generator) -> np.ndarray:
    """The same estimator `evaluate_signed_signal` uses, via prefix sums over whole blocks."""
    n = f.size
    length = min(block, n)
    n_blocks = int(np.ceil(n / length))
    d2, f2 = np.concatenate([d, d]), np.concatenate([f, f])
    p_df = np.concatenate([[0.0], np.cumsum(d2 * f2)])
    p_d = np.concatenate([[0.0], np.cumsum(d2)])
    p_abs = np.concatenate([[0.0], np.cumsum(np.abs(d2))])
    p_f = np.concatenate([[0.0], np.cumsum(f2)])
    starts = np.arange(n)
    blk = [p[starts + length] - p[starts] for p in (p_df, p_d, p_abs, p_f)]
    pick = rng.integers(0, n, size=(n_boot, n_blocks))
    t_df, t_d, t_abs, t_f = (b[pick].sum(axis=1) for b in blk)
    with np.errstate(invalid="ignore", divide="ignore"):
        per_event = t_df / np.maximum(t_abs, 1.0)
        net = t_d / np.maximum(t_abs, 1.0)
        drift = t_f / (n_blocks * length)
        return np.where(t_abs > 0, per_event - net * drift, np.nan)


def coverage_at(pool: np.ndarray, n_blocks: int, reps: int, rng: np.random.Generator,
                block: int = DEFAULT_BLOCK, n_boot: int = 600) -> np.ndarray:
    """Actual coverage of the percentile interval, one value per nominal α in ALPHA_GRID.

    Each replication draws a CONTIGUOUS window of real returns, so the tail and the serial
    dependence are the market's own rather than a model's.
    """
    n = n_blocks * block
    if pool.size < n + 1:
        return np.full(ALPHA_GRID.size, np.nan)
    covered = np.zeros(ALPHA_GRID.size)
    usable = 0
    for _ in range(reps):
        start = int(rng.integers(0, pool.size - n))
        f = pool[start:start + n]
        d = np.zeros(n)
        k = max(int(n * SIGNAL_RATE), 2)
        where = rng.choice(n, size=k, replace=False)
        d[where] = rng.choice([-1.0, 1.0], size=k)      # independent of f: true shift is 0
        boot = _block_bootstrap_signed(d, f, n_boot, block, rng)
        boot = boot[np.isfinite(boot)]
        if boot.size < 50:
            continue
        usable += 1
        lo = np.percentile(boot, 100 * ALPHA_GRID / 2)
        hi = np.percentile(boot, 100 * (1 - ALPHA_GRID / 2))
        covered += (lo <= 0.0) & (0.0 <= hi)
    return covered / usable if usable else np.full(ALPHA_GRID.size, np.nan)


def alpha_for_target(coverage: np.ndarray,
                     target: float = TARGET_COVERAGE) -> float | None:
    """Interpolate the nominal α whose true coverage equals `target`.

    Coverage falls as α rises, so the grid is searched from tight to loose for the crossing.
    Returns None when even the tightest α under-covers — which is a finding, not a default.
    """
    ok = np.isfinite(coverage)
    if not ok.any():
        return None
    a, c = ALPHA_GRID[ok], coverage[ok]
    if c[0] < target:
        return None                       # tightest α on the grid still under-covers
    for i in range(1, a.size):
        if c[i] < target <= c[i - 1]:
            span = c[i - 1] - c[i]
            w = (c[i - 1] - target) / span if span > 0 else 0.0
            return float(a[i - 1] + w * (a[i] - a[i - 1]))
    return float(a[-1])                   # never drops below target on this grid


@dataclass
class CoverageRow:
    """One calibration cell.

    NOT slots=True: the full coverage curve is serialised to the cache so the cells can be
    POOLED afterwards. At 2,000 replications the Monte Carlo error on a coverage near 95%
    is +/-0.96 points, which is the same size as the differences between cells — so no
    single cell resolves the mapping, and only the pooled curve does.
    """

    product: str
    horizon: int
    n_blocks: int
    coverage_at_05: float
    alpha_star: float | None
    reps: int
    coverage: list[float] = field(default_factory=list)


def run_alpha(products: Sequence[str], horizons: Sequence[int], reps: int,
              seed: int, ckpt: "Checkpoint | None" = None) -> list[CoverageRow]:
    ckpt = ckpt or Checkpoint(CKPT_ALPHA)
    rows: list[CoverageRow] = []
    idx05 = int(np.argmin(np.abs(ALPHA_GRID - 0.05)))
    for product in products:
        for horizon in horizons:
            pool = None
            print(f"  {product} {horizon}m")
            for nb in BLOCK_COUNTS:
                key = Checkpoint.key("alpha", product, horizon, nb, reps, seed)
                cached = ckpt.get(key)
                if cached is not None:
                    cov = np.array(cached)
                else:
                    if pool is None:
                        pool = return_pool(product, horizon)
                        print(f"     pool {pool.size:,} returns")
                    rng = np.random.default_rng(
                        cell_seed(seed, "alpha", product, horizon, nb))
                    cov = coverage_at(pool, nb, reps, rng)
                    ckpt.put(key, [float(x) for x in cov])
                star = alpha_for_target(cov)
                rows.append(CoverageRow(product, horizon, nb, float(cov[idx05]), star,
                                        reps, [float(x) for x in cov]))
                mark = "  [ckpt]" if cached is not None else ""
                print(f"     blocks {nb:>5}: coverage at α=0.05 = {cov[idx05]:.3%}"
                      + (f"   α* = {star:.4f}" if star else "   α* = NOT REACHABLE")
                      + mark)
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# B. detection floor
# ══════════════════════════════════════════════════════════════════════════════


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def series_from_pool(pool: np.ndarray, n: int, effect: float,
                     rng: np.random.Generator) -> np.ndarray:
    """A real-return series with a known edge injected.

    The base is a CONTIGUOUS window of real returns, so the noise carries the true tail.
    The edge is a slow regime that flips roughly every 500 bars — the same construction the
    crypto sweep used, chosen because an edge flipping every bar would be invisible to a
    moving-average family at any amplitude and would measure the signal family instead of
    the pipeline.
    """
    start = int(rng.integers(0, max(pool.size - n, 1)))
    base = pool[start:start + n].copy()
    if base.size < n:
        base = np.resize(base, n)
    sd = base.std(ddof=1)
    state = np.sign(np.sin(np.arange(n) / 500.0))
    return base + state * effect * sd


def power_curve(pool: np.ndarray, effects: Sequence[float], n: int, reps: int,
                seed: int, horizons: Sequence[int],
                ckpt: "Checkpoint | None" = None, tag: str = "") -> list[dict]:
    rows: list[dict] = []
    for eff in effects:
        key = Checkpoint.key("floor", tag, n, reps, f"{eff:.10g}")
        cached = ckpt.get(key) if ckpt else None
        if cached is not None:
            rows.append(cached)
            print(f"      effect {eff:>7.4f}x  promoted "
                  f"{cached['promote_rate'] * reps:>3.0f}/{reps}  [ckpt]")
            continue
        promoted = 0
        for i in range(reps):
            rng = np.random.default_rng(cell_seed(seed, "floor", n, f"{eff:.6g}", i))
            series = series_from_pool(pool, n, eff, rng)
            result = run_pipeline(series, rng=rng, horizons=tuple(horizons),
                                  n_bootstrap=200, n_permutations=200)
            promoted += 0 if result.found_nothing else 1
        lo, hi = wilson(promoted, reps)
        row = {"effect": float(eff), "n": n, "reps": reps,
               "promote_rate": promoted / reps, "ci": [lo, hi]}
        if ckpt:
            ckpt.put(key, row)
        rows.append(row)
        print(f"      effect {eff:>7.4f}x  promoted {promoted:>3}/{reps} "
              f"({promoted / reps:.0%}, CI {lo:.0%}-{hi:.0%})")
    return rows


def detection_floor(rows: list[dict], target: float = POWER_TARGET) -> dict:
    passing = [r for r in rows if r["promote_rate"] >= target]
    if not passing:
        return {"floor": None,
                "bracket_low": max((r["effect"] for r in rows), default=None)}
    first = min(passing, key=lambda r: r["effect"])
    below = [r for r in rows if r["effect"] < first["effect"]]
    return {"floor": first["effect"], "floor_rate": first["promote_rate"],
            "bracket_low": max((r["effect"] for r in below), default=None)}


def scaling_exponent(points: Sequence[tuple[int, float]]) -> dict:
    pts = [(n, f) for n, f in points if f]
    if len(pts) < 2:
        return {"exponent": None, "n_points": len(pts)}
    x = np.log([p[0] for p in pts])
    y = np.log([p[1] for p in pts])
    slope, intercept = np.polyfit(x, y, 1)
    return {"exponent": float(slope), "intercept": float(intercept),
            "n_points": len(pts), "matches_sqrt_n": bool(abs(slope + 0.5) < 0.15)}


# ══════════════════════════════════════════════════════════════════════════════
# reporting
# ══════════════════════════════════════════════════════════════════════════════


CRYPTO_ALPHA: Final[dict[int, float]] = {50: 0.0312, 100: 0.0359, 250: 0.0400, 500: 0.0500}
CRYPTO_FLOOR: Final[float] = 0.1592
CRYPTO_EXPONENT: Final[float] = -0.321


def render_alpha(rows: list[CoverageRow], reps: int) -> str:
    w: list[str] = []
    a = w.append
    a("# Stage 1 bootstrap α — re-measured on futures")
    a("")
    a("Generated by `python -m futuresres.integrity.calibration --part alpha`. "
      "CLAUDE_FUTURES.md §4, §5 Stage 1.")
    a("")
    a(f"{reps:,} replications per cell. Each draws a **contiguous window of real returns**, "
      f"so the tail and the serial dependence are the market's own rather than a model's. "
      f"The statistic is the signed shift `evaluate_signed_signal` computes, "
      f"block-bootstrapped with the same {DEFAULT_BLOCK}-bar blocks.")
    a("")
    a(f"Monte Carlo error on a coverage near 95% at {reps:,} reps is about "
      f"±{100 * 1.96 * (0.95 * 0.05 / reps) ** 0.5:.2f} points.")
    a("")
    for horizon in sorted({r.horizon for r in rows}):
        a(f"## {horizon}-minute horizon")
        a("")
        a("| product | blocks | coverage at α=0.05 | α* for true 95% | crypto α* |")
        a("|---|---|---|---|---|")
        for r in [x for x in rows if x.horizon == horizon]:
            star = f"{r.alpha_star:.4f}" if r.alpha_star is not None else "**unreachable**"
            crypto = CRYPTO_ALPHA.get(r.n_blocks)
            a(f"| {r.product} | {r.n_blocks} | {r.coverage_at_05:.2%} | {star} | "
              f"{crypto if crypto else '—'} |")
        a("")
    return "\n".join(w)


# ══════════════════════════════════════════════════════════════════════════════
# B. detection floor — the sweep
# ══════════════════════════════════════════════════════════════════════════════

#: The crypto effect ladder, so floors are directly comparable rather than merely similar.
EFFECT_GRID: Final[tuple[float, ...]] = tuple(
    float(x) for x in np.geomspace(0.001, 0.30, 10)
)


def nonoverlapping_pool(product: str, horizon: int) -> np.ndarray:
    """Non-overlapping h-minute returns — one observation per h minutes.

    A DELIBERATE DIFFERENCE FROM THE α CALIBRATION, which uses the OVERLAPPING series
    because that is literally what `evaluate_signed_signal` receives.

    For the floor, overlapping windows would misstate the answer in both directions at
    once: `n` would count observations that share 179/180 of their content, and the
    effect size would be quoted against the volatility of an overlapping window. Taking
    every h-th return makes `n` the number of INDEPENDENT observations the sample can
    supply, which is the quantity that has to be compared against how much data exists.
    """
    r = return_pool(product, horizon)
    return r[::horizon] if horizon > 1 else r


def sample_ladder(pool_size: int) -> list[int]:
    """Three log-spaced sample sizes that the pool can actually supply.

    Capped at half the pool so a contiguous window is always available, and floored at
    2,000 so the smallest rung is not pure noise.
    """
    hi = min(80_000, pool_size // 2)
    lo = max(2_000, hi // 16)
    if hi <= lo:
        return [max(2_000, pool_size // 2)]
    return [int(round(x)) for x in np.geomspace(lo, hi, 3)]


def run_floor(products: Sequence[str], horizons: Sequence[int], seed: int,
              reps_small: int = 25, reps_large: int = 15,
              ckpt: "Checkpoint | None" = None) -> list[dict]:
    """Sweep effect size at three sample lengths, per product and horizon."""
    ckpt = ckpt or Checkpoint(CKPT_FLOOR)
    out: list[dict] = []
    for product in products:
        for horizon in horizons:
            pool = nonoverlapping_pool(product, horizon)
            sizes = sample_ladder(pool.size)
            available = pool.size
            print(f"\n  {product} {horizon}m: {available:,} independent observations "
                  f"available; sweeping n = {sizes}")
            points: list[tuple[int, float]] = []
            curves: list[dict] = []
            for n in sizes:
                reps = reps_small if n <= 20_000 else reps_large
                grid = EFFECT_GRID if n <= 20_000 else EFFECT_GRID[::2]
                print(f"    [n = {n:,}]  {len(grid)} rungs x {reps} reps")
                curve = power_curve(pool, grid, n, reps, seed,
                                    horizons=_pipeline_horizons(horizon),
                                    ckpt=ckpt, tag=f"{product}-{horizon}")
                fl = detection_floor(curve)
                points.append((n, fl.get("floor")))
                curves.append({"n": n, "reps": reps, "floor": fl.get("floor"),
                               "bracket_low": fl.get("bracket_low"), "curve": curve})
                print(f"      -> floor " + (f"{fl['floor']:.4g}x"
                                            if fl.get("floor") else "outside the grid"))
            fit = scaling_exponent(points)
            out.append({"product": product, "horizon": horizon,
                        "available": available, "sizes": sizes,
                        "curves": curves, "fit": fit})
            if fit.get("exponent") is not None:
                print(f"    exponent {fit['exponent']:+.3f} "
                      f"({'matches' if fit['matches_sqrt_n'] else 'does NOT match'} sqrt-n)")
    return out


def _pipeline_horizons(horizon: int) -> tuple[int, ...]:
    """Forward horizons for the search family, in units of the series' own bar.

    At the 1-minute series these are the crypto values. At an aggregated series a "bar" is
    already h minutes, so the same wall-clock horizons would be absurd (240 bars of 180
    minutes is a month); the family is scaled to a comparable number of BARS instead.
    """
    return (10, 60, 240) if horizon == 1 else (1, 4, 12)


def extrapolate(fit: dict, n: int) -> float | None:
    if fit.get("exponent") is None:
        return None
    return float(np.exp(fit["intercept"] + fit["exponent"] * np.log(n)))


def render_floor(results: list[dict]) -> str:
    w: list[str] = []
    a = w.append
    a("# Detection floor — re-measured on futures")
    a("")
    a("Generated by `python -m futuresres.integrity.calibration --part floor`. "
      "CLAUDE_FUTURES.md §7.")
    a("")
    a("Smallest injected effect the pipeline promotes end-to-end at **>= 80%**, in units of "
      "**one bar's volatility at the horizon being swept**. Below the floor a null carries "
      "no information, because nothing would have been found either way.")
    a("")
    a("The noise is a **contiguous window of real returns**, so the tail and the clustering "
      "are the market's own. The injected edge is a slow regime flipping every ~500 bars — "
      "the crypto construction, chosen because an edge flipping every bar would be "
      "invisible to a moving-average family at any amplitude and would measure the signal "
      "family rather than the pipeline.")
    a("")
    a(f"> **Observations are NON-OVERLAPPING here**, unlike the α calibration. `n` counts "
      f"independent h-minute returns, which is what has to be compared against how much "
      f"data exists. Overlapping windows would inflate `n` by a factor of h while quoting "
      f"the effect against an overlapping window's volatility.")
    a("")

    a("## Floors")
    a("")
    a("| product | horizon | independent obs available | n swept | floor | vs crypto 0.1592x |")
    a("|---|---|---|---|---|---|")
    for r in results:
        for c in r["curves"]:
            fl = c["floor"]
            rel = f"{fl / CRYPTO_FLOOR:.2f}x" if fl else "—"
            a(f"| {r['product']} | {r['horizon']}m | {r['available']:,} | {c['n']:,} | "
              + (f"**{fl:.4g}x**" if fl else "outside grid") + f" | {rel} |")
    a("")

    a("## Scaling with sample size")
    a("")
    a(f"Crypto measured **{CRYPTO_EXPONENT:+.3f}**, not the -0.5 that root-n would give. "
      f"The same fit here:")
    a("")
    a("| product | horizon | exponent | matches sqrt-n? | floor at the full sample |")
    a("|---|---|---|---|---|")
    for r in results:
        fit = r["fit"]
        exp = fit.get("exponent")
        if exp is None:
            a(f"| {r['product']} | {r['horizon']}m | — | — | — |")
            continue
        full = extrapolate(fit, r["available"])
        a(f"| {r['product']} | {r['horizon']}m | **{exp:+.3f}** | "
          f"{'yes' if fit['matches_sqrt_n'] else '**no**'} | "
          + (f"{full:.4g}x" if full else "—") + " |")
    a("")
    a("The full-sample column is an EXTRAPOLATION from three points and is quoted as an "
      "optimistic bound, not a measurement — the floors sit on grid rungs, so each carries "
      "roughly half a rung of resolution, and the ladder is 1.885x per rung.")
    a("")

    a("## Curves")
    a("")
    for r in results:
        a(f"### {r['product']} {r['horizon']}m")
        a("")
        a("| n | " + " | ".join(f"{e:.4g}" for e in EFFECT_GRID) + " |")
        a("|" + "---|" * (len(EFFECT_GRID) + 1))
        for c in r["curves"]:
            by = {row["effect"]: row["promote_rate"] for row in c["curve"]}
            cells = " | ".join(
                (f"{by[e]:.0%}" if e in by else "·") for e in EFFECT_GRID
            )
            a(f"| {c['n']:,} | {cells} |")
        a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.integrity.calibration")
    ap.add_argument("--part", choices=["alpha", "floor"], required=True)
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260829)
    ap.add_argument("--products", nargs="*", default=list(PRODUCTS))
    ap.add_argument("--horizons", nargs="*", type=int, default=list(HORIZONS))
    args = ap.parse_args(argv)

    if args.part == "alpha":
        rows = run_alpha(args.products, args.horizons, args.reps, args.seed)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        out = REPORT.with_name("calibration_alpha.md")
        out.write_text(render_alpha(rows, args.reps), encoding="utf-8")
        CACHE.write_text(json.dumps([r.__dict__ for r in rows], indent=2), encoding="utf-8")
        print(f"wrote {out}")
        return 0

    results = run_floor(args.products, args.horizons, args.seed)
    out = REPORT.with_name("calibration_floor.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_floor(results), encoding="utf-8")
    CACHE.with_name("floor_cache.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
