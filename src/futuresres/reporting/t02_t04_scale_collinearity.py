"""T02/T03/T04 pre-registration checks. T_SERIES_CANDIDATES.md Class B. A MEASUREMENT: no
trial spent; logs one record per product to `measurements.jsonl` with `--log`.

    python -m futuresres.reporting.t02_t04_scale_collinearity --product INDEX
    python -m futuresres.reporting.t02_t04_scale_collinearity --product MGC
    python -m futuresres.reporting.t02_t04_scale_collinearity --log

INDEX is the spliced NQ -> MNQ series (2010-2026), not MNQ alone: MNQ begins in May 2019, so
an MNQ-only run cannot see the 2010-2018 era at all, and the era check is the point. J, ER and
RSkew depend on PRICE only, and NQ and MNQ quote the same index points on the same 0.25 tick
(`reports/splice.md` verifies the convention), so the splice is valid for these quantities in a
way it is NOT for volume-based ones (decisions.md S54).

One product per process: the 4.7M-row splice is the largest series on disk.

FOUR THINGS, each answering a question the brief or the draft raised.

1. Conditioner correlation, Spearman rho(J, ER) at each shared W in {30, 60, 120}, on
   NON-OVERLAPPING windows (end index a multiple of W). Rolling windows share W-1 of their W
   returns, so the first run's rho over every window (+0.05 to +0.08) used millions of
   observations carrying almost no independent information - and needed memory the 4.7M-row
   splice does not have. Firing rates are still counted over every window.

2. FIRING OVERLAP, which is the test that actually matters. The Q01/Q02 precedent (S59) did not
   stop at a conditioner correlation; it measured P(Q02 long | Q01 fires). Here: at each
   (W, j_low, e_high), P(T02 fires), P(T04 fires), P(both), the independence benchmark, Jaccard
   and the two conditionals. Both entries fade the same W-window move, so whenever both fire
   they take the SAME direction by construction - overlap of firings is overlap of trades.
   T04's `|net| > k x ATR` clause is omitted: the draft never fixes k or which ATR, and
   inventing one would be choosing a parameter. Stated, not hidden.

3. DOES T02'S CONDITION SELECT ANYTHING? P(J < j_low) per threshold. A condition true in most
   windows is the L11/L05 degenerate case (S40-S41), and finding that here costs nothing.

4. SCALE INVARIANCE, VERIFIED BY ERA (2010-2018, 2019-2023, 2024-2026). J and RSkew are ratios
   of moments of ONE return series over ONE window, so a price-level factor cancels
   algebraically - but that argument covers only multiplicative scale. It says nothing about
   price DISCRETENESS: on a fixed tick grid a rising price shrinks the tick in bps, changing how
   often a 1-minute return is exactly zero. Bipower variation sums PRODUCTS of adjacent |r|,
   so every zero kills two terms while realised variance loses one. If zeros are common, J is
   inflated, and by an amount that drifts with price. So the zero-return share and the tick in
   bps are reported by era beside J, which is what lets a drift be ATTRIBUTED rather than only
   observed.
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl
from scipy.stats import spearmanr

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
RESULT_JSON: Final[Path] = ROOT / "reports" / "t02_t04_scale_collinearity.json"
REPORT_MD: Final[Path] = ROOT / "reports" / "t02_t04_scale_collinearity.md"

SERIES: Final[dict[str, str]] = {"INDEX": "NQ_MNQ_spliced", "MGC": "MGC"}
TICK: Final[dict[str, float]] = {"INDEX": 0.25, "MGC": 0.10}
W_GRID: Final[tuple[int, ...]] = (30, 60, 120)
J_LOW: Final[tuple[float, ...]] = (0.1, 0.2, 0.3)
E_HIGH: Final[tuple[float, ...]] = (0.5, 0.65, 0.8)
ERAS: Final[tuple[tuple[str, int, int], ...]] = (
    ("2010-2018", 2010, 2018), ("2019-2023", 2019, 2023), ("2024-2026", 2024, 2026),
)


def load(product: str, lo: int, hi: int) -> dict[str, np.ndarray]:
    """One era's sessions only. A window never crosses a session, so splitting at era
    boundaries (which fall between sessions) changes no window - and it divides the peak
    by ~3, which the 4.7M-row splice needs: run whole, it was OOM-killed."""
    df = (pl.scan_parquet(CONTINUOUS / f"{SERIES[product]}.parquet")
          .select("contract", "session", "close")
          .filter(pl.col("session").dt.year().is_between(lo, hi))
          .collect(engine="streaming"))
    out = {
        "close": df["close"].to_numpy(),
        "contract": df["contract"].cast(pl.Categorical).to_physical().to_numpy(),
        "session": df["session"].to_physical().to_numpy(),
    }
    del df
    gc.collect()
    return out


def rolling_sum(x: np.ndarray, w: int) -> np.ndarray:
    """Trailing sum of the last w values; NaN unless all w are finite.

    A first version took `cumsum(x)` directly and relied on NaN "propagating" to mark windows
    that cross a boundary. It does not propagate locally: one NaN poisons EVERY later prefix
    sum, so every window after the first session boundary came back NaN, and so did every
    statistic built on them - caught on 2026-10-02 because the output was all NaN, before
    anything was read from it. Sum and count are now accumulated separately.
    """
    ok = np.isfinite(x)
    c = np.concatenate([[0.0], np.cumsum(np.where(ok, x, 0.0))])
    k = np.concatenate([[0], np.cumsum(ok)])
    out = np.full(x.size, np.nan)
    full = (k[w:] - k[:-w]) == w
    out[w - 1:] = np.where(full, c[w:] - c[:-w], np.nan)
    return out


def era_windows(product: str, lo: int, hi: int) -> tuple[dict, dict]:
    """Per-era return facts, and per-W (J, ER, RSkew) arrays for that era."""
    s = load(product, lo, hi)
    close, con, ses = s["close"], s["contract"], s["session"]
    n = close.size
    same1 = np.zeros(n, bool)
    same1[1:] = (con[1:] == con[:-1]) & (ses[1:] == ses[:-1])
    logp = np.log(close)
    r = np.full(n, np.nan)
    r[1:] = logp[1:] - logp[:-1]
    r[~same1] = np.nan
    fin = np.isfinite(r)
    facts = {"bars": int(fin.sum()), "zero_return_share": float(np.mean(r[fin] == 0.0)),
             "tick_bps_median": float(np.median(TICK[product] / close * 1e4))}
    del logp, close, con, ses, same1, s
    abs_r = np.abs(r)
    prod_adj = np.full(n, np.nan)
    prod_adj[1:] = abs_r[1:] * abs_r[:-1]
    per_w = {}
    for w in W_GRID:
        # a window is valid only if all w returns exist, i.e. no session or contract boundary
        # inside it; `rolling_sum` enforces that by count, and the bipower term needs w-1 products.
        rv = rolling_sum(r * r, w)
        bv = (np.pi / 2.0) * rolling_sum(prod_adj, w - 1)
        absum = rolling_sum(abs_r, w)
        ok = np.isfinite(rv) & np.isfinite(bv) & np.isfinite(absum) & (rv > 0) & (absum > 0)
        # windows ending on a multiple of w never share a return: the sample for rho
        nonov = (np.flatnonzero(ok) % w) == 0
        J = np.clip(rv[ok] - bv[ok], 0, None) / rv[ok]
        del bv
        ER = np.abs(rolling_sum(r, w)[ok]) / absum[ok]
        del absum
        SK = np.sqrt(w) * rolling_sum(r ** 3, w)[ok] / rv[ok] ** 1.5
        del rv, ok
        per_w[w] = (J, ER, SK, nonov)
        gc.collect()
    import resource
    print(f"    {product} {lo}-{hi}: peak RSS "
          f"{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB", flush=True)
    return facts, per_w


def run(product: str) -> dict:
    era_facts, pooled = {}, {w: ([], []) for w in W_GRID}
    counts = {w: {f"{jl}/{eh}": np.zeros(4) for jl in J_LOW for eh in E_HIGH} for w in W_GRID}
    totals = {w: 0 for w in W_GRID}
    zeros = {w: 0 for w in W_GRID}
    era_stats: dict[int, dict] = {w: {} for w in W_GRID}
    for name, lo, hi in ERAS:
        facts, per_w = era_windows(product, lo, hi)
        if facts["bars"] < 1000:
            continue
        era_facts[name] = facts
        for w, (J, ER, SK, nonov) in per_w.items():
            pooled[w][0].append(J[nonov].copy())
            pooled[w][1].append(ER[nonov].copy())
            totals[w] += J.size
            zeros[w] += int((J == 0.0).sum())
            for jl in J_LOW:
                t02 = J < jl
                for eh in E_HIGH:
                    t04 = ER > eh
                    counts[w][f"{jl}/{eh}"] += [t02.sum(), t04.sum(), (t02 & t04).sum(),
                                                (t02 | t04).sum()]
            era_stats[w][name] = {
                "windows": int(J.size),
                "J_median": float(np.median(J)), "J_mean": float(J.mean()),
                "J_zero_share": float(np.mean(J == 0.0)),
                "p_J_below_0.2": float(np.mean(J < 0.2)),
                "ER_median": float(np.median(ER)),
                "RSkew_median": float(np.median(SK)),
                "RSkew_p10_p90": [float(v) for v in np.percentile(SK, [10, 90])],
            }
        del per_w
        gc.collect()

    per_w_out = {}
    for w in W_GRID:
        J = np.concatenate(pooled[w][0])
        ER = np.concatenate(pooled[w][1])
        pooled[w] = None
        rho = float(spearmanr(J, ER).statistic)
        rho_n = J.size
        del J, ER
        gc.collect()
        n = totals[w]
        fire = {}
        for key, (a2, a4, both, union) in counts[w].items():
            p2, p4, pb = a2 / n, a4 / n, both / n
            fire[key] = {"p_t02": p2, "p_t04": p4, "p_both": pb, "indep": p2 * p4,
                         "jaccard": both / union if union else float("nan"),
                         "p_t02_given_t04": both / a4 if a4 else float("nan"),
                         "p_t04_given_t02": both / a2 if a2 else float("nan")}
        per_w_out[w] = {"windows": int(n), "rho_windows_nonoverlapping": int(rho_n),
                        "rho_J_ER": rho, "J_zero_share": zeros[w] / n,
                        "fire": fire, "era": era_stats[w]}
    return {"product": product, "series": SERIES[product], "era_returns": era_facts,
            "by_window": per_w_out}


def render(res: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# T02/T03/T04 — collinearity, firing overlap, selectivity and scale, before registration")
    a("")
    a("Generated by `python -m futuresres.reporting.t02_t04_scale_collinearity`. A "
      "measurement, **no trial spent**. INDEX is the spliced NQ→MNQ series (2010–2026); "
      "these statistics use price only, which the splice preserves. See the module "
      "docstring for definitions.")
    a("")
    a("## 1. Conditioner correlation, Spearman ρ(J, ER)")
    a("")
    a("| product | W | all windows | non-overlapping windows (ρ sample) | ρ |")
    a("|---|---|---|---|---|")
    for p, r in res.items():
        for wv, d in sorted(r["by_window"].items(), key=lambda kv: int(kv[0])):
            a(f"| {p} | {wv} | {d['windows']:,} | {d['rho_windows_nonoverlapping']:,} | "
              f"{d['rho_J_ER']:+.4f} |")
    a("")
    a("## 2. Firing overlap at W = 60 (both entries fade the same move, so a shared firing "
      "is a shared trade)")
    a("")
    a("| product | j_low / e_high | P(T02) | P(T04) | P(both) | if independent | Jaccard | P(T02 \\| T04) |")
    a("|---|---|---|---|---|---|---|---|")
    for p, r in res.items():
        f = r["by_window"]["60"]["fire"] if "60" in r["by_window"] else r["by_window"][60]["fire"]
        for key, v in f.items():
            a(f"| {p} | {key} | {v['p_t02']:.3f} | {v['p_t04']:.4f} | {v['p_both']:.4f} | "
              f"{v['indep']:.4f} | {v['jaccard']:.4f} | {v['p_t02_given_t04']:.3f} |")
    a("")
    a("## 3. Scale: J against price discreteness, by era (W = 60)")
    a("")
    a("| product | era | tick (bps) | zero 1m returns | J median | J = 0 exactly | P(J < 0.2) | ER median | RSkew median | RSkew p10 / p90 |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for p, r in res.items():
        bw = r["by_window"]["60"] if "60" in r["by_window"] else r["by_window"][60]
        for era, e in bw["era"].items():
            b = r["era_returns"].get(era, {})
            a(f"| {p} | {era} | {b.get('tick_bps_median', float('nan')):.2f} | "
              f"{b.get('zero_return_share', float('nan')):.3f} | {e['J_median']:.4f} | "
              f"{e['J_zero_share']:.3f} | {e['p_J_below_0.2']:.3f} | {e['ER_median']:.4f} | "
              f"{e['RSkew_median']:+.4f} | {e['RSkew_p10_p90'][0]:+.2f} / "
              f"{e['RSkew_p10_p90'][1]:+.2f} |")
    a("")
    return "\n".join(w)


def log_measurements(res: dict) -> None:
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "measurements.jsonl")
    for p, r in res.items():
        bw = r["by_window"]
        w60 = bw["60"] if "60" in bw else bw[60]
        mid = w60["fire"]["0.2/0.65"]
        rec = log.append(Trial(
            trial_id=log.next_id("m"), hypothesis_id="T02/T04", symbol=p,
            date_range=("2010-06-06", "2026-08-27"), status="completed",
            params={"kind": "t_series_precheck",
                    "rho_J_ER": {str(k): v["rho_J_ER"] for k, v in bw.items()},
                    "w60_mid_cell": mid,
                    "w60_J_median_by_era": {e: v["J_median"] for e, v in w60["era"].items()},
                    "zero_return_share_by_era": {e: v["zero_return_share"]
                                                 for e, v in r["era_returns"].items()}},
            note=("kind=measurement; NOT a trial and NOT counted in N. T-series S1-S2 "
                  "precheck: J/ER conditioner correlation, firing overlap, T02 selectivity "
                  "and scale by era against price discreteness. decisions.md 65."),
        ))
        print(f"logged {rec['trial_id']} ({p})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.t02_t04_scale_collinearity")
    ap.add_argument("--product", choices=list(SERIES))
    ap.add_argument("--log", action="store_true")
    args = ap.parse_args(argv)
    res: dict = {}
    if RESULT_JSON.exists():
        res = json.loads(RESULT_JSON.read_text(encoding="utf-8"))
    if args.product:
        out = run(args.product)
        res[args.product] = json.loads(json.dumps(out))      # normalise keys to str
    # The MNQ-only first run is superseded by INDEX, which spans the era it could not see, and
    # any entry in the first run's schema (no firing overlap, no discreteness) is stale.
    res.pop("MNQ", None)
    res = {k: v for k, v in res.items()
           if all("fire" in w for w in v.get("by_window", {}).values())}
    RESULT_JSON.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    REPORT_MD.write_text(render(res), encoding="utf-8")
    print(f"wrote {RESULT_JSON.name} and {REPORT_MD.name}")
    if args.log:
        log_measurements(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
