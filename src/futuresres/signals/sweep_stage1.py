"""Shared Stage 1 machinery for sweep-and-reclaim hypotheses (L02-absorption, L03, L04).

THE STATISTIC IS (REAL - PLACEBO), NEVER (REAL - 0). Price reacts at arbitrary levels, so a
raw reclaim statistic is not evidence that the level matters. The placebo is the null as
redefined in `decisions.md` 37: an arbitrary REGION at a matched distance, carrying the same
scale as the real level it is paired with.

WHY THESE THREE SHARE A RUNNER. L03 and L04 are the same condition on different level types -
prior-day extremes against session extremes - and L02's surviving arm is that condition on
opening-range boundaries. One implementation means one place for the pairing, the bootstrap
and the permutation to be right or wrong, rather than three that drift.

THE PLACEBO RUNS THE SAME CONDITION AT ITS OWN LOCATION, AND TAKES ITS OWN DIRECTION. This
differs deliberately from L07, where the placebo inherited the real zone's traded direction.
There the direction was a property of the GAP, so holding it fixed isolated location. Here
the direction is a property of the EVENT - which side price happened to penetrate - so
forcing the real level's side onto the placebo would compare a reclaim against a
counterfactual that never happened. The claim under test is "this condition pays more at a
real level than at an arbitrary one", and that requires running the condition at both.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Final

import numpy as np

from futuresres.levels import definitions as D
from futuresres.levels.placebo import make_region_placebo
from futuresres.signals.stage1 import calibrated_alpha

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
RATES: Final[Path] = ROOT / "reports" / "level_rates.json"

#: reports/calibration.md, round-trip both sides.
COST_BPS: Final[dict[str, float]] = {"MNQ": 0.48, "MGC": 0.65}
FLOOR_BPS: Final[dict[tuple[str, int], float]] = {
    ("MNQ", 60): 2.57, ("MNQ", 120): 15.66, ("MNQ", 180): 15.66,
    ("MGC", 60): 4.17, ("MGC", 120): 14.34, ("MGC", 180): 14.34,
}

ALPHA: Final[float] = 0.05
N_BOOT: Final[int] = 2000
N_PERM: Final[int] = 2000
MIN_EVENTS: Final[int] = 100

M_GRID: Final[tuple[int, ...]] = (2, 4, 8)
K_GRID: Final[tuple[int, ...]] = (2, 3, 5)
#: H=180 ONLY, PRE-REGISTERED. At H=60 the detection floor is 5,620 events on MGC and every
#: cell of every one of these hypotheses is below it, so those cells cannot reach a verdict
#: and spending trials on them buys nothing. 60 and 120 are WITHDRAWN, not parked; testing
#: them later is a new registration. decisions.md 41.
HOLDS: Final[tuple[int, ...]] = (180,)


@dataclass(slots=True)
class Cell:
    product: str
    hypothesis: str
    level_type: str
    m: int
    k: int
    horizon: int
    excluded: bool = False
    reason: str = ""
    events: int = 0
    real_bps: float = float("nan")
    placebo_bps: float = float("nan")
    diff_bps: float = float("nan")
    ci_low: float = float("nan")
    ci_high: float = float("nan")
    p_value: float = float("nan")
    separated: bool = False
    bh_survivor: bool = False
    cost_bps: float = float("nan")
    diff_over_cost: float = float("nan")
    detection_floor_bps: float = float("nan")
    entry_minute_sd: float = float("nan")
    real_dir_up_share: float = float("nan")


def matched_types(path: Path = RATES) -> dict[tuple[str, str], dict]:
    m = json.loads(path.read_text(encoding="utf-8"))["match"]
    return {(x["level_type"], x["product"]): x for x in m}


def benjamini_hochberg(p: np.ndarray, alpha: float = ALPHA) -> np.ndarray:
    p = np.asarray(p, float)
    n = p.size
    if n == 0:
        return np.zeros(0, bool)
    order = np.argsort(p)
    passed = p[order] <= alpha * (np.arange(1, n + 1) / n)
    keep = np.zeros(n, bool)
    if passed.any():
        keep[order[: int(np.flatnonzero(passed).max()) + 1]] = True
    return keep


def _signed_return_bps(g: D.Grid, row: np.ndarray, entry: np.ndarray,
                       traded_dir: np.ndarray, horizon: int) -> np.ndarray:
    """Signed log return from the entry close to min(entry + horizon, 15:55 ET), in bps."""
    out = np.full(row.size, np.nan)
    for i in range(row.size):
        e = int(entry[i])
        if e < 0 or traded_dir[i] == 0:
            continue
        x = min(e + horizon, D.RTH_EXIT, D.ROW_MINUTES - 1)
        if x <= e:
            continue
        p0, p1 = g.close[row[i], e], g.close[row[i], x]
        if p0 > 0 and p1 > 0:
            out[i] = traded_dir[i] * np.log(p1 / p0) * 1e4
    return out


def paired_stats(real: np.ndarray, plac: np.ndarray, rows: np.ndarray,
                 rng: np.random.Generator) -> tuple[float, ...]:
    """Paired real-minus-placebo, session bootstrap, paired permutation. As L07 (38).

    THE BOOTSTRAP RESAMPLES SESSIONS, NOT EVENTS, because a session's reclaims are
    correlated and resampling events would report an interval far too narrow.
    THE PERMUTATION SWAPS REAL AND PLACEBO WITHIN A PAIR: under the null that the level
    carries no information, which member of a pair is real is exchangeable.
    """
    ok = np.isfinite(real) & np.isfinite(plac)
    r, p_, s = real[ok], plac[ok], rows[ok]
    n = r.size
    if n < MIN_EVENTS:
        return (float("nan"),) * 5 + (n, float("nan"))

    d = r - p_
    obs = float(d.mean())
    idx_by_session = {int(v): np.flatnonzero(s == v) for v in np.unique(s)}
    keys = list(idx_by_session)
    boot = np.empty(N_BOOT)
    for b in range(N_BOOT):
        pick = rng.integers(0, len(keys), len(keys))
        boot[b] = d[np.concatenate([idx_by_session[keys[i]] for i in pick])].mean()
    eff_alpha = calibrated_alpha(max(len(keys), 2))
    lo, hi = np.percentile(boot, [100 * eff_alpha / 2, 100 * (1 - eff_alpha / 2)])

    null = np.empty(N_PERM)
    for i in range(N_PERM):
        null[i] = float((d * (rng.integers(0, 2, n) * 2 - 1)).mean())
    pval = float(np.mean(np.abs(null) >= abs(obs)))
    return float(r.mean()), float(p_.mean()), obs, float(lo), float(hi), n, pval


LevelFactory = Callable[[D.Grid], D.LevelSet]


def evaluate(hypothesis: str, product: str, specs: list[tuple[str, LevelFactory]],
             g: D.Grid, rng: np.random.Generator) -> list[Cell]:
    """One hypothesis, one product: every (level type, m, k, horizon) cell.

    An unmatched level type is recorded as an EXCLUDED cell with the reason, never dropped by
    omission - a type that vanishes from a report is indistinguishable from one nobody
    thought of (decisions.md 37).
    """
    mt = matched_types()
    cells: list[Cell] = []

    for level_type, factory in specs:
        rec = mt.get((level_type, product))
        ok = rec is not None and not rec.get("failures")
        if not ok:
            why = "no matching record" if rec is None else "; ".join(rec["failures"])[:200]
            for m in M_GRID:
                for k in K_GRID:
                    for h in HOLDS:
                        cells.append(Cell(product, hypothesis, level_type, m, k, h,
                                          excluded=True,
                                          reason=f"EXCLUDED, placebo unmatched: {why}"))
            print(f"    {product} {hypothesis} {level_type}: EXCLUDED - {why}", flush=True)
            continue

        lv = factory(g)
        scale = D.window_scale(g, lv)
        good = np.isfinite(lv.price) & np.isfinite(scale) & (scale > 0)
        if good.sum() < MIN_EVENTS:
            continue
        price, row = lv.price[good], lv.row[good]
        valid, ref = lv.valid_from[good], lv.ref_price[good]
        sub = D.LevelSet(lv.kind, price, row, valid, ref)
        placebo_px = make_region_placebo(price, ref, g.days[row], level_type, scale[good])
        plac = D.LevelSet(lv.kind, placebo_px, row, valid, ref)

        for m in M_GRID:
            for k in K_GRID:
                fr, mr, dr = D.sweep_reclaim_directed(g, sub, m, k, product)
                fp, mp, dp = D.sweep_reclaim_directed(g, plac, m, k, product)
                # The registered trade is COUNTER to the penetration.
                traded_r, traded_p = -dr, -dp
                for h in HOLDS:
                    rr = _signed_return_bps(g, row, mr, traded_r, h)
                    pp = _signed_return_bps(g, row, mp, traded_p, h)
                    rmean, pmean, diff, lo, hi, n, pv = paired_stats(rr, pp, row, rng)
                    sep = bool(np.isfinite(lo) and np.isfinite(hi)
                               and (lo > 0 or hi < 0) and pv < ALPHA)
                    cost = COST_BPS[product]
                    ent = mr[fr]
                    cells.append(Cell(
                        product, hypothesis, level_type, m, k, h, events=n,
                        real_bps=rmean, placebo_bps=pmean, diff_bps=diff,
                        ci_low=lo, ci_high=hi, p_value=pv, separated=sep, cost_bps=cost,
                        diff_over_cost=(abs(diff) / cost if np.isfinite(diff) else float("nan")),
                        detection_floor_bps=FLOOR_BPS[(product, h)],
                        entry_minute_sd=float(ent.std()) if ent.size > 1 else float("nan"),
                        real_dir_up_share=(float((dr[fr] > 0).mean())
                                           if fr.any() else float("nan")),
                    ))
                    c = cells[-1]
                    print(f"    {product} {hypothesis} {level_type} m={m} k={k} H={h}: "
                          f"n={c.events:,} diff={c.diff_bps:+.4f} bps "
                          f"minute_sd={c.entry_minute_sd:.1f} "
                          f"up={c.real_dir_up_share:.2f}", flush=True)
    return cells


def apply_bh(cells: list[Cell]) -> None:
    """BH WITHIN the hypothesis, across every test actually performed.

    Excluded cells are not tests and are left out: including them would inflate the
    denominator with things nobody looked at, weakening the correction rather than
    strengthening it.
    """
    live = [c for c in cells if not c.excluded and np.isfinite(c.p_value)]
    if not live:
        return
    for c, keep in zip(live, benjamini_hochberg(np.array([c.p_value for c in live]))):
        c.bh_survivor = bool(keep) and c.separated
