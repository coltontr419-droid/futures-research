"""A40 - the NKD-corn theme stress-tested, and set against the deployed NKD dollar-week rule (decisions.md 504). No trial.

    python -m futuresres.reporting.a40_nkdcorn
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a27_standalone as a27
import futuresres.reporting.a35_nkddollar as a35
import futuresres.reporting.a38_d246 as a38
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
PER = {"2010-20": (dt.date(2010, 1, 1), dt.date(2020, 12, 31)), "2021-24": DISC, "2025-26": (dt.date(2025, 1, 1), dt.date(2026, 8, 31))}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def tenday(S: dict) -> dict:
    ds = sorted(S); r = np.array([S[d] for d in ds])
    return {ds[i]: float(r[i - 9:i + 1].sum()) for i in range(9, len(ds))}


def corn(source: str) -> tuple[dict, float]:
    W = tenday(d111.predictor("ZC=F") if source == "ZC=F" else a38._oc("CORN"))
    return W, float(np.median([abs(v) for d, v in W.items() if DISC[0] <= d <= DISC[1]]))


def independent() -> dict:
    out = {}
    T = {"A21 window": d111.target("NKD"), "NKD=F": a35.nikkei("NKD=F")}
    for src in ("ZC=F", "CORN"):
        W, med = corn(src)
        for tn, Y in T.items():
            for form in ("all", "strong"):
                for pn, (lo, hi) in PER.items():
                    g = np.array([-np.sign(W[d3.prev_weekday(d)]) * y - 0.2 for d, y in Y.items() if lo <= d <= hi and d3.prev_weekday(d) in W
                                  and W[d3.prev_weekday(d)] != 0 and (form == "all" or abs(W[d3.prev_weekday(d)]) > med)])
                    k = f"{src:5} -> {tn:10} | {form:6} | {pn}"
                    out[k] = {"n": int(len(g)), "net": float(g.mean()), "t": _t(g)}
                    print(f"{k}: n {len(g):4} net {g.mean():+6.2f} t {_t(g):+5.2f}", flush=True)
    return out


def accounts() -> dict:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; n, rt = a23.MARKETS["NKD"]; Wc, med = corn("ZC=F"); Wd = a35.weak_dollar_week("6E=F"); out = {}
    (h, l, c), d = a23.market_paths("NKD", "post"); dd = [x.astype(object) for x in d]
    cs = np.array([Wc.get(d3.prev_weekday(v), 0.0) for v in dd]); ds_ = np.array([Wd.get(d3.prev_weekday(v), 0.0) for v in dd])
    dollar_short = ds_ < 0
    corn_short = (cs > med)                                  # fade a strong corn rise
    strong_corn = np.abs(cs) > med
    agree = np.mean((np.sign(ds_) == -np.sign(cs))[strong_corn & (ds_ != 0)])
    print(f"agreement (dollar-week side == corn side on strong-corn days): {agree:.0%}", flush=True)
    out["agreement"] = float(agree)
    base = a23.replay(s, (h, l, c), n, rt)
    st = np.array([dd[i] for i in base["start"]]); k25 = st >= dt.date(2025, 1, 1)
    corn_side_short = strong_corn & (cs > 0)
    disagree = strong_corn & (dollar_short != corn_side_short)
    variants = {"plan": (None, None), "dollar-week (deployed)": (dollar_short, None), "corn (D343 form)": (corn_short, None),
                "dollar-week, flat when strong corn disagrees": (dollar_short, disagree)}
    rng = np.random.default_rng(504)
    for name, (mask, skip) in variants.items():
        r = base if mask is None else a23.replay(s, a27.flip(h, l, c, mask), n, rt, skip=skip)
        row = {"mean_net": float(r["net"].mean()), "p_payout": float((r["first"] > 0).mean()), "p_pos": float((r["net"] > 0).mean()),
               "mean_net_2025": float(r["net"][k25].mean()), "p_payout_2025": float((r["first"][k25] > 0).mean()), "p_pos_2025": float((r["net"][k25] > 0).mean())}
        if mask is not None:
            null = []; null25 = []
            for _ in range(30):
                rn = a23.replay(s, a27.flip(h, l, c, rng.permutation(mask)), n, rt, skip=skip)
                null.append(rn["net"].mean()); null25.append(rn["net"][k25].mean())
            row["pct_vs_random"] = float((np.array(null) < row["mean_net"]).mean() * 100); row["pct_vs_random_2025"] = float((np.array(null25) < row["mean_net_2025"]).mean() * 100)
        out[name] = row
        print(f"NKD {name:45}: 2021-26 {row['mean_net']:+7,.0f} P(pay) {row['p_payout']:.0%} P(>0) {row['p_pos']:.0%} | 2025 starts {row['mean_net_2025']:+7,.0f} "
              f"P(pay) {row['p_payout_2025']:.0%} P(>0) {row['p_pos_2025']:.0%}" + (f" | vs random {row['pct_vs_random']:.0f}% / {row['pct_vs_random_2025']:.0f}%" if mask is not None else ""), flush=True)
    return out


def main(argv=None) -> int:
    res = {"independent": independent(), "accounts": accounts()}
    (ROOT / "reports" / "a40_nkdcorn.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
