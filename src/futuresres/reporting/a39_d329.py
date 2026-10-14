"""A39 - D329 (crude reverses an extreme stretch against gasoline) stress-tested (decisions.md 495). No trial.

    python -m futuresres.reporting.a39_d329
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
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d127_regime as d127
import futuresres.reporting.d3_relay as d3
from futuresres.data import daily_bars as db

ROOT = Path(__file__).resolve().parents[3]
PER = {"2010-20": (dt.date(2010, 1, 1), dt.date(2020, 12, 31)), "2021-24": (dt.date(2021, 1, 1), dt.date(2024, 12, 31)),
       "2025-26": (dt.date(2025, 1, 1), dt.date(2026, 8, 31))}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def z(partner: str) -> dict:
    a = dict(zip(*d127.closes("CL=F"))); b = dict(zip(*d127.closes(partner)))
    ds = sorted(d for d in a if d in b and a[d] and b[d] and a[d] > 0 and b[d] > 0)
    x = np.log(np.array([a[d] for d in ds]) / np.array([b[d] for d in ds])); out = {}
    for i in range(20, len(ds)):
        w = x[i - 20:i]; sd = w.std(ddof=1)
        if sd > 0 and np.isfinite(x[i]):
            out[ds[i]] = float((x[i] - w.mean()) / sd)
    return out


def owned_cl() -> dict:
    m = db.load_market("CL"); ret = np.asarray(m.ret); cx = np.asarray(m.crossover)
    return {d.astype(object): float(r) * 1e4 for d, r, c in zip(m.dates, ret, cx) if not c and np.isfinite(r)}


def independent() -> dict:
    out = {}
    T = {"Yahoo session": (d111.target("CL"), 0.7), "owned close-close": (owned_cl(), 0.7)}
    for partner in ("RB=F", "HO=F"):
        Z = z(partner)
        for k in (1.5, 2.0, 2.5):
            for tn, (Y, cost) in T.items():
                for pn, (lo, hi) in PER.items():
                    g = np.array([-np.sign(Z[d3.prev_weekday(d)]) * y - cost for d, y in Y.items() if lo <= d <= hi
                                  and d3.prev_weekday(d) in Z and abs(Z[d3.prev_weekday(d)]) > k])
                    key = f"vs {partner:4} | z>{k} | {tn:17} | {pn}"
                    out[key] = {"n": int(len(g)), "net": float(g.mean()) if len(g) else None, "t": _t(g)}
                    print(f"{key}: n {len(g):3} net {g.mean() if len(g) else float('nan'):+7.2f} t {_t(g):+5.2f}", flush=True)
    return out


def overlay() -> dict:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; n, rt = a23.MARKETS["MCL"]; Z = z("RB=F"); out = {}
    for era in ("pre", "post"):
        (h, l, c), d = a23.market_paths("MCL", era); dd = [x.astype(object) for x in d]
        zz = np.array([Z.get(d3.prev_weekday(v), 0.0) for v in dd]); mask = zz > 2.0
        base = a23.replay(s, (h, l, c), n, rt); rule = a23.replay(s, a27.flip(h, l, c, mask), n, rt)
        st = np.array([dd[i] for i in base["start"]]); k25 = st >= dt.date(2025, 1, 1)
        rng = np.random.default_rng(495); null = []; null25 = []
        for _ in range(40):
            rn = a23.replay(s, a27.flip(h, l, c, rng.permutation(mask)), n, rt)
            null.append(rn["net"].mean() - base["net"].mean())
            if k25.any():
                null25.append(rn["net"][k25].mean() - base["net"][k25].mean())
        null = np.array(null); d_ = rule["net"].mean() - base["net"].mean()
        row = {"short_share": float(mask.mean()), "plan_mean": float(base["net"].mean()), "rule_mean": float(rule["net"].mean()),
               "plan_p_payout": float((base["first"] > 0).mean()), "rule_p_payout": float((rule["first"] > 0).mean()),
               "plan_p_pos": float((base["net"] > 0).mean()), "rule_p_pos": float((rule["net"] > 0).mean()),
               "null_mean": float(null.mean()), "null_sd": float(null.std(ddof=1)), "pct": float((null < d_).mean() * 100)}
        msg = (f"MCL {era}: short {mask.mean():.1%} | plan {row['plan_mean']:+7,.0f} P(pay) {row['plan_p_payout']:.0%} P(>0) {row['plan_p_pos']:.0%} | rule "
               f"{row['rule_mean']:+7,.0f} P(pay) {row['rule_p_payout']:.0%} P(>0) {row['rule_p_pos']:.0%} | Δ {d_:+,.0f} vs random {null.mean():+,.0f} ± {null.std(ddof=1):,.0f} "
               f"(beats {row['pct']:.0f}%)")
        if k25.any():
            null25 = np.array(null25); d25 = rule["net"][k25].mean() - base["net"][k25].mean()
            row.update({"plan_mean_2025": float(base["net"][k25].mean()), "rule_mean_2025": float(rule["net"][k25].mean()),
                        "plan_p_pos_2025": float((base["net"][k25] > 0).mean()), "rule_p_pos_2025": float((rule["net"][k25] > 0).mean()),
                        "pct_2025": float((null25 < d25).mean() * 100)})
            msg += (f"\n   starts 2025+: plan {row['plan_mean_2025']:+7,.0f} P(>0) {row['plan_p_pos_2025']:.0%} | rule {row['rule_mean_2025']:+7,.0f} "
                    f"P(>0) {row['rule_p_pos_2025']:.0%} | beats {row['pct_2025']:.0f}% of random flips")
        out[era] = row; print(msg, flush=True)
    return out


def main(argv=None) -> int:
    res = {"independent": independent(), "overlay": overlay()}
    (ROOT / "reports" / "a39_d329.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
