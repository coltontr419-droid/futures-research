"""A44 - where inside the window do the deployed dollar rules earn? (decisions.md 545). No trial.

    python -m futuresres.reporting.a44_subwin
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.a35_nkddollar as a35
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
PER = {"2010-20": (dt.date(2010, 1, 1), dt.date(2020, 12, 31)), "2021-24": (dt.date(2021, 1, 1), dt.date(2024, 12, 31)),
       "2025-26": (dt.date(2025, 1, 1), dt.date(2026, 8, 31))}
SPEC = {"DAX": ("grxeur", "Europe/Berlin", {"t0900": (9, 0), "t1130": (11, 30), "t1400": (14, 0), "t1730": (17, 30)},
                {"09:00-11:30": ("t0900", "t1130"), "11:30-14:00": ("t1130", "t1400"), "14:00-17:30": ("t1400", "t1730"), "whole": ("t0900", "t1730")}, 0.3),
        "NKD": ("jpxjpy", "Asia/Tokyo", {"t0900": (9, 0), "t1130": (11, 30), "t1230": (12, 30), "t1500": (15, 0)},
                {"morning": ("t0900", "t1130"), "afternoon": ("t1230", "t1500"), "whole": ("t0900", "t1500")}, 0.2)}


def signs(mkt: str) -> dict:
    return d111.predictor("DX-Y.NYB") if mkt == "DAX" else a35.weak_dollar_week("6E=F")


def run() -> dict:
    out = {}
    for mkt, (sym, tz, times, wins, cost) in SPEC.items():
        f = d3.histdata(sym, {k: (tz, *v) for k, v in times.items()}).drop_nulls().filter(__import__("polars").col("date").dt.weekday() <= 5)
        P = signs(mkt); ds = f["date"].to_list()
        for wn, (a, b) in wins.items():
            r = ((f[b] / f[a] - 1) * 1e4).to_numpy(); md = np.median(r); rs = 1.4826 * np.median(np.abs(r - md))
            for per, (lo, hi) in PER.items():
                g = np.array([np.sign(P[q]) * x - cost for d, x in zip(ds, r) if lo <= d <= hi and abs(x - md) <= 15 * rs
                              and (q := d3.prev_weekday(d)) in P and P[q]])
                row = {"n": int(len(g)), "net": float(g.mean()), "sd": float(g.std(ddof=1)), "sharpe": float(g.mean() / g.std(ddof=1)),
                       "t": float(g.mean() / g.std(ddof=1) * math.sqrt(len(g)))}
                out[f"{mkt} {wn} | {per}"] = row
                print(f"{mkt} {wn:12} {per}: n {row['n']:4} net {row['net']:+6.2f} sd {row['sd']:6.1f} Sharpe/trade {row['sharpe']:+.3f} t {row['t']:+5.2f}", flush=True)
    return out


def main(argv=None) -> int:
    (ROOT / "reports" / "a44_subwin.json").write_text(json.dumps(run(), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def morning_paths(era: str):
    """NKD Tokyo-morning paths (09:00 -> 11:30): the first 150 minutes of A21's window paths, drift re-removed within the era."""
    import futuresres.reporting.a21_more_accounts as a21
    h, l, c, d = a21.paths("NKD", era)
    h, l, c = (x[:, :150].astype(np.float64) for x in (h, l, c))
    ramp = c[:, -1].mean() * np.arange(1, 151) / 150
    return tuple((x - ramp).astype(np.float32) for x in (h, l, c)), np.asarray(d).astype("datetime64[D]")


def replay(n_random: int = 100) -> dict:
    import warnings
    import futuresres.reporting.a23_account_sizes as a23
    import futuresres.reporting.a27_standalone as a27
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; n, rt = a23.MARKETS["NKD"]; P = signs("NKD"); out = {}
    for era in ("pre", "post"):
        for wn, ((h, l, c), d) in (("whole", a23.market_paths("NKD", era)), ("morning", morning_paths(era))):
            dd = [x.astype(object) for x in d]; st = np.array(dd[: len(dd) - 84]); m25 = st >= dt.date(2025, 1, 1)
            short = np.array([P.get(d3.prev_weekday(v), 0.0) for v in dd]) < 0
            base = a23.replay(s, (h, l, c), n, rt); r = a23.replay(s, a27.flip(h, l, c, short), n, rt)
            rng = np.random.default_rng(545); rnd = np.array([a23.replay(s, a27.flip(h, l, c, rng.permutation(short)), n, rt)["net"] for _ in range(n_random)])
            row = {"plan_mean": float(base["net"].mean()), "rule_mean": float(r["net"].mean()), "rule_p_payout": float((r["first"] > 0).mean()),
                   "beats_random_pct": float((rnd.mean(1) < r["net"].mean()).mean() * 100)}
            if m25.any():
                row.update({"plan_2025": float(base["net"][m25].mean()), "rule_2025": float(r["net"][m25].mean()), "rule_p_payout_2025": float((r["first"][m25] > 0).mean()),
                            "plan_p_payout_2025": float((base["first"][m25] > 0).mean()), "beats_random_2025_pct": float((rnd[:, m25].mean(1) < r["net"][m25].mean()).mean() * 100)})
            out[f"NKD {era} {wn}"] = row
            print(f"NKD {era} {wn:8}: plan {row['plan_mean']:+7,.0f} | rule {row['rule_mean']:+7,.0f} P {row['rule_p_payout']:.0%} beats {row['beats_random_pct']:.0f}%"
                  + (f" | 2025 starts plan {row['plan_2025']:+7,.0f} ({row['plan_p_payout_2025']:.0%}) rule {row['rule_2025']:+7,.0f} ({row['rule_p_payout_2025']:.0%}) beats {row['beats_random_2025_pct']:.0f}%" if m25.any() else ""), flush=True)
    return out

