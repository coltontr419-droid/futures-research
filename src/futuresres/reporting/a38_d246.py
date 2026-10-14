"""A38 - D246 (MNQ fades a strong week in semiconductors) stress-tested (decisions.md 485). No trial.

    python -m futuresres.reporting.a38_d246
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
import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d24_shock as d24
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
PER = {"2010-20": (dt.date(2010, 1, 1), dt.date(2020, 12, 31)), "2021-24": DISC, "2025-26": (dt.date(2025, 1, 1), dt.date(2026, 8, 31))}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def _oc(sym):
    z = a22.load(sym, "1d").with_columns(pl.col("ts").dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5).unique("date", keep="last").sort("date")
    r = ((z["c"] / z["o"] - 1) * 1e4).to_numpy(); md = np.nanmedian(r); rs = 1.4826 * np.nanmedian(np.abs(r - md))
    return {d: float(x) for d, x in zip(z["date"].to_list(), r) if np.isfinite(x) and abs(x - md) <= 15 * rs}


def week(S):
    ds = sorted(S); r = np.array([S[d] for d in ds])
    return {ds[i]: float(r[i - 4:i + 1].sum()) for i in range(4, len(ds))}


def signal(pred: str) -> tuple[dict, float]:
    W = week(d111.predictor("SMH") if pred == "SMH" else _oc("^SOX"))
    med = float(np.median([abs(v) for d, v in W.items() if DISC[0] <= d <= DISC[1]]))
    return W, med


def independent() -> dict:
    out = {}
    T = {"MNQ grid": d111.target("MNQ"), "NQ=F": _oc("NQ=F")}
    for pred in ("SMH", "^SOX"):
        W, med = signal(pred)
        for tn, Y in T.items():
            for pn, (lo, hi) in PER.items():
                g = np.array([-np.sign(W[d3.prev_weekday(d)]) * y - 0.5 for d, y in Y.items() if lo <= d <= hi and d3.prev_weekday(d) in W
                              and abs(W[d3.prev_weekday(d)]) > med])
                k = f"{pred:5} -> {tn:8} | {pn}"
                out[k] = {"n": int(len(g)), "net": float(g.mean()), "t": _t(g)}
                print(f"{k}: n {len(g):4} net {g.mean():+6.2f} t {_t(g):+5.2f}", flush=True)
    return out


def overlay() -> dict:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; n, rt = a23.MARKETS["MNQ"]; W, med = signal("SMH")
    sh = d24.shocks(d10.series(), "ZN")
    nxt = lambda d: d + dt.timedelta(days=1 if d.weekday() < 4 else 3)
    zn_short = {nxt(d) for d, q in sh.items() if q[1] and q[0] < 0}; zn_long = {nxt(d) for d, q in sh.items() if q[1] and q[0] > 0}
    out = {}
    for era in ("pre", "post"):
        (h, l, c), d = a23.market_paths("MNQ", era); dd = [x.astype(object) for x in d]
        w = np.array([W.get(d3.prev_weekday(v), 0.0) for v in dd])
        d246 = (w > med)                                                 # short after a strong semis rally week
        d68 = np.array([v in zn_short for v in dd])
        combo = np.where(np.array([v in zn_short or v in zn_long for v in dd]), d68, d246)
        base = a23.replay(s, (h, l, c), n, rt)
        st = np.array([dd[i] for i in base["start"]]); k25 = st >= dt.date(2025, 1, 1)
        for name, mask in (("plan", None), ("D68 (deployed)", d68), ("D246", d246), ("D246 + D68", combo)):
            r = base if mask is None else a23.replay(s, a27.flip(h, l, c, mask), n, rt)
            row = {"mean_net": float(r["net"].mean()), "p_payout": float((r["first"] > 0).mean()), "p_pos": float((r["net"] > 0).mean())}
            if era == "post":
                row.update({"mean_net_2025": float(r["net"][k25].mean()), "p_payout_2025": float((r["first"][k25] > 0).mean()), "p_pos_2025": float((r["net"][k25] > 0).mean())})
            out[f"{era} | {name}"] = row
            extra = f" | 2025 starts {row['mean_net_2025']:+7,.0f} P(pay) {row['p_payout_2025']:.0%} P(>0) {row['p_pos_2025']:.0%}" if era == "post" else ""
            print(f"MNQ {era} {name:15}: mean {row['mean_net']:+7,.0f} P(pay) {row['p_payout']:.0%} P(>0) {row['p_pos']:.0%}{extra}", flush=True)
        rng = np.random.default_rng(485); null = []
        for _ in range(40):
            rn = a23.replay(s, a27.flip(h, l, c, rng.permutation(d246)), n, rt); null.append(rn["net"].mean() - base["net"].mean())
        d_rule = out[f"{era} | D246"]["mean_net"] - base["net"].mean(); null = np.array(null)
        out[f"{era} | calibration"] = {"rule_delta": float(d_rule), "null_mean": float(null.mean()), "null_sd": float(null.std(ddof=1)), "pct": float((null < d_rule).mean() * 100)}
        print(f"MNQ {era} calibration: D246 Δ {d_rule:+,.0f} vs random {null.mean():+,.0f} ± {null.std(ddof=1):,.0f} -> beats {(null < d_rule).mean():.0%}", flush=True)
    return out


def main(argv=None) -> int:
    res = {"independent": independent(), "overlay": overlay()}
    (ROOT / "reports" / "a38_d246.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
