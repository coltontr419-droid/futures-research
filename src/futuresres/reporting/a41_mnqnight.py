"""A41 - the MNQ-night fade theme (D397-D401) stress-tested (decisions.md 514). No trial.

Independent data: other soy / AUD series as predictors; QQQ's 16:00 -> 09:30 gap as the target. Then an MNQ account that trades
the night session (18:00 -> 09:30 ET) under the plan's brackets, with and without the rule, against random flips.

    python -m futuresres.reporting.a41_mnqnight
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np
import polars as pl

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a27_standalone as a27
import futuresres.reporting.d141_mnqwin as d141
import futuresres.reporting.d3_relay as d3
import futuresres.reporting.d8_intraday as d8

ROOT = Path(__file__).resolve().parents[3]
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
PER = {"2010-20": (dt.date(2010, 1, 1), dt.date(2020, 12, 31)), "2021-24": DISC, "2025-26": (dt.date(2025, 1, 1), dt.date(2026, 8, 31))}
PREDS = ("SOYB", "ZS=F", "ZM=F", "ZL=F", "DBA", "6A=F")


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def oc(sym: str) -> dict:
    if sym == "DBA":
        z = a22.load(sym, "1d").with_columns(pl.col("ts").dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5).unique("date", keep="last").sort("date")
        return {d: float(x) for d, x in zip(z["date"].to_list(), ((z["c"] / z["o"] - 1) * 1e4).to_numpy())}
    return d141.d111.predictor(sym)


def soy_vote() -> dict:
    A, B, C = oc("SOYB"), oc("ZM=F"), oc("6A=F")
    return {d: float(np.sign(A.get(d, 0)) + np.sign(B.get(d, 0)) + np.sign(C.get(d, 0))) for d in set(A) | set(B) | set(C)}


def qqq_gap() -> dict:
    z = a22.load("QQQ", "1d").with_columns(pl.col("ts").dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5).unique("date", keep="last").sort("date")
    o, c = z["o"].to_numpy(), z["c"].to_numpy(); ds = z["date"].to_list()
    return {ds[i]: float((o[i] / c[i - 1] - 1) * 1e4) for i in range(1, len(ds)) if (ds[i] - ds[i - 1]).days <= 4}


def independent() -> dict:
    out = {}; targets = {"MNQ night": d141.target("mnq_night"), "QQQ gap": qqq_gap()}
    preds = {p: oc(p) for p in PREDS}; preds["vote SOYB+ZM+6A"] = soy_vote()
    for pn, P in preds.items():
        for tn, Y in targets.items():
            for per, (lo, hi) in PER.items():
                g = np.array([-np.sign(P[d3.prev_weekday(d)]) * y - 0.5 for d, y in Y.items() if lo <= d <= hi and P.get(d3.prev_weekday(d))])
                k = f"fade {pn:15} -> {tn:9} | {per}"; out[k] = {"n": int(len(g)), "net": float(g.mean()), "t": _t(g)}
                print(f"{k}: n {len(g):4} net {g.mean():+6.2f} t {_t(g):+5.2f}", flush=True)
    return out


def night_paths(era: str):
    """One-contract GROSS $ minute-close paths (h = l = c) for the night session, drift removed within the era."""
    days, C, _, K = d8.load("MNQ", "night")
    keep = []; P = []
    for i, d in enumerate(days):
        if (era == "post") != (d >= dt.date(2021, 1, 1)):
            continue
        c = C[i]; f = np.isfinite(c)
        if f.sum() < 800 or not f[0] or K[i, 0] != K[i, np.where(f)[0][-1]]:
            continue
        c = c.copy()
        for j in range(1, len(c)):
            if not np.isfinite(c[j]):
                c[j] = c[j - 1]
        P.append(c / c[0] - 1); keep.append(d)
    p = np.array(P, np.float64)
    p = p - p[:, -1].mean() * (np.arange(1, p.shape[1] + 1) / p.shape[1])
    usd = float(C[np.isfinite(C[:, -1]), -1][-1]) * 2.0
    p = (p * usd).astype(np.float32)
    return (p, p, p), np.array(keep)


def overlay(n_random: int = 200) -> dict:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; n, rt = a23.MARKETS["MNQ"]; out = {}
    rules = {"D397 fade SOYB (every day)": oc("SOYB"), "D398 fade SOYB (strong only)": None, "vote SOYB+ZM+6A (every day)": soy_vote()}
    S1 = oc("SOYB"); med = float(np.median([abs(v) for d, v in S1.items() if DISC[0] <= d <= DISC[1]]))
    for era in ("pre", "post"):
        (h, l, c), d = night_paths(era)
        base = a23.replay(s, (h, l, c), n, rt)
        out[f"{era} | plan (night, long)"] = row = {"p_payout": float((base["first"] > 0).mean()), "mean_net": float(base["net"].mean()), "p_net_positive": float((base["net"] > 0).mean())}
        print(f"MNQ night {era} plan            : P(payout) {row['p_payout']:.0%} mean {row['mean_net']:+7,.0f} P(net>0) {row['p_net_positive']:.0%} ({len(d)} sessions)", flush=True)
        for name, P in rules.items():
            if P is None:
                x = np.array([S1.get(d3.prev_weekday(v), 0.0) for v in d]); short = (x > 0) & (np.abs(x) > med)
            else:
                x = np.array([P.get(d3.prev_weekday(v), 0.0) for v in d]); short = x > 0
            r = a23.replay(s, a27.flip(h, l, c, short), n, rt)
            rng = np.random.default_rng(514); rnd = []
            for _ in range(n_random):
                m = rng.permutation(short); rnd.append(a23.replay(s, a27.flip(h, l, c, m), n, rt)["net"].mean())
            rnd = np.array(rnd)
            row = {"p_payout": float((r["first"] > 0).mean()), "mean_net": float(r["net"].mean()), "p_net_positive": float((r["net"] > 0).mean()),
                   "short_share": float(short.mean()), "random_mean": float(rnd.mean()), "beats_random_pct": float((rnd < r["net"].mean()).mean() * 100)}
            out[f"{era} | {name}"] = row
            print(f"MNQ night {era} {name:28}: P(payout) {row['p_payout']:.0%} mean {row['mean_net']:+7,.0f} P(net>0) {row['p_net_positive']:.0%} "
                  f"short {row['short_share']:.0%} | random {row['random_mean']:+7,.0f}, beats {row['beats_random_pct']:.0f}%", flush=True)
        if era == "post":                         # the sealed window alone (starts in 2025)
            m25 = np.array([v >= dt.date(2025, 1, 1) for v in d])[: len(d) - 84]
            for name, P in (("plan", None), ("D397", oc("SOYB"))):
                pp = (h, l, c) if P is None else a27.flip(h, l, c, np.array([P.get(d3.prev_weekday(v), 0.0) for v in d]) > 0)
                r = a23.replay(s, pp, n, rt); k = f"post 2025 starts | {name}"
                out[k] = {"p_payout": float((r["first"][m25] > 0).mean()), "mean_net": float(r["net"][m25].mean())}
                print(f"MNQ night {k}: P(payout) {out[k]['p_payout']:.0%} mean {out[k]['mean_net']:+7,.0f}", flush=True)
    return out


def main(argv=None) -> int:
    res = {"independent": independent(), "overlay": overlay()}
    (ROOT / "reports" / "a41_mnqnight.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
