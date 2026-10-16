"""A58 - Apex Trader Funding 50K against Tradeify's 50K Daily (decisions.md 621). No trial.

    python -m futuresres.reporting.a58_apex
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a27_standalone as a27
import futuresres.reporting.a43_scale as a43
import futuresres.reporting.a47_book as a47

ROOT = Path(__file__).resolve().parents[3]
START, DD, TARGET = 50_000.0, 2_000.0, 3_000.0
EVAL_FEE, ACTIVATION = 25.0, 120.0
CAPS = (1_500.0, 1_500.0, 2_000.0, 2_500.0, 2_500.0, 3_000.0)
LOCK_PEAK, LOCK_FLOOR, SAFETY = 52_100.0, 50_100.0, 52_100.0
TAKES, STOPS = (600, 800, 1_000, 1_200), (500, 600, 800, 1_000)


def bracket(h, l, c, W, L, cost):
    """Net P&L of one day: take W / stop L net of cost (stop fills at the stop)."""
    hw = np.where(h >= W + cost)[0]; hl = np.where(l <= -(L - cost))[0]
    tw = hw[0] if len(hw) else 10 ** 9; tl = hl[0] if len(hl) else 10 ** 9
    if tl < 10 ** 9 and tl <= tw:
        return -L
    if tw < 10 ** 9:
        return W
    return float(c[-1]) - cost


def apex(H, Lo, C, n, rt, W, L, window=84):
    cost = rt * n; S = len(C); nets, firsts = [], []
    for s0 in range(S - window):
        fees = EVAL_FEE; paid = 0.0; first = -1; phase = 0; eq = pk = START; k = 0; wins = 0; cyc = 0.0; best = 0.0
        for dd in range(window):
            i = s0 + dd
            floor = pk - DD if phase == 0 or pk < LOCK_PEAK else LOCK_FLOOR
            room = eq - floor
            if room <= cost + 10:
                fees += EVAL_FEE; phase = 0; eq = pk = START; k = 0; wins = 0; cyc = 0.0; best = 0.0; continue
            pnl = bracket(H[i] * n, Lo[i] * n, C[i] * n, W, min(L, room - 1), cost)
            eq += pnl; pk = max(pk, eq)
            if eq <= floor:
                fees += EVAL_FEE; phase = 0; eq = pk = START; k = 0; wins = 0; cyc = 0.0; best = 0.0; continue
            if phase == 0:
                if eq - START >= TARGET:
                    fees += ACTIVATION; phase = 1; eq = pk = START; wins = 0; cyc = 0.0; best = 0.0
                continue
            cyc += pnl; best = max(best, pnl); wins += pnl >= 250
            if wins >= 5 and cyc > 0 and best <= 0.5 * cyc:
                amt = min(CAPS[k], eq - SAFETY)
                if amt >= 500:
                    paid += amt; eq -= amt; k += 1; wins = 0; cyc = 0.0; best = 0.0
                    first = dd + 1 if first < 0 else first
                    if k == len(CAPS):                     # sixth payout: the account closes; a new evaluation
                        fees += EVAL_FEE; phase = 0; eq = pk = START; k = 0
        nets.append(paid - fees); firsts.append(first)
    return np.array(nets), np.array(firsts)


def main() -> int:
    warnings.filterwarnings("ignore"); s = a23.specs()["50K Daily"]; R = a43.masks()
    sh = __import__("futuresres.reporting.d24_shock", fromlist=["x"]); d10 = __import__("futuresres.reporting.d10_universe", fromlist=["x"])
    zs = sh.shocks(d10.series(), "ZN"); nxt = lambda d: d + dt.timedelta(days=1 if d.weekday() < 4 else 3)
    zn_short = {nxt(d) for d, q in zs.items() if q[1] and q[0] < 0}
    rule = {"MNQ": lambda v: v in zn_short, "NKD": R["NKD"], "FDXM": R["FDXM"], "MGC": None, "MCL": None}
    out = {}; book = {}
    for mkt in ("MNQ", "MGC", "MCL", "NKD", "FDXM"):
        n, rt = a23.MARKETS[mkt]
        picks = {}
        for era in ("post", "pre"):                    # brackets chosen on 2021-24 starts, then applied unchanged to 2010-20
            (h, l, c), d = a23.market_paths(mkt, era); dd = [x.astype(object) for x in d]
            if rule[mkt] is not None:
                h, l, c = a27.flip(h, l, c, np.array([rule[mkt](v) for v in dd]))
            st = dd[: len(dd) - 84]; m24 = np.array([x < dt.date(2025, 1, 1) for x in st])
            res = {}
            for W, L in itertools.product(TAKES, STOPS):
                na, fa = apex(h, l, c, n, rt, W, L)
                rt_ = a23.replay(s, (h, l, c), n, rt, fixed=(W, L))
                res[(W, L)] = (na, fa, rt_["net"], rt_["first"])
            pol = a23.replay(s, (h, l, c), n, rt)
            if era == "post":
                picks["a"] = max(res, key=lambda k: res[k][0][m24].mean()); picks["t"] = max(res, key=lambda k: res[k][2][m24].mean())
            pick_a, pick_t = picks["a"], picks["t"]
            book.setdefault(era, {})[mkt] = {"dates": st, "apex": res[pick_a][0], "tradeify_fixed": res[pick_t][2], "tradeify_policy": pol["net"],
                                             "apex_first": res[pick_a][1], "tpol_first": pol["first"]}
            out[f"{mkt} {era}"] = {"apex_brackets": list(pick_a), "tradeify_brackets": list(pick_t)}
            print(f"{mkt} {era}: Apex best {pick_a} | Tradeify fixed best {pick_t}", flush=True)
    for per, era, lo, hi in (("2010-20", "pre", dt.date(2010, 1, 1), dt.date(2020, 12, 31)), ("2021-26", "post", dt.date(2021, 1, 1), dt.date(2026, 12, 31)),
                             ("2025 starts", "post", dt.date(2025, 1, 1), dt.date(2026, 12, 31))):
        B = book[era]; idx = {m: {d: i for i, d in enumerate(B[m]["dates"])} for m in B}
        ds = sorted(d for d in set.intersection(*(set(idx[m]) for m in B)) if lo <= d <= hi)
        row = {}
        for key in ("apex", "tradeify_fixed", "tradeify_policy"):
            per_acct = {m: float(np.mean([B[m][key][idx[m][d]] for d in ds])) for m in B}
            tot = np.array([sum(B[m][key][idx[m][d]] for m in B) for d in ds])
            row[key] = {"book": float(tot.mean()), "p_pos": float((tot > 0).mean()), "p10": float(np.percentile(tot, 10)), "per_account": per_acct}
        pay = {m: float(np.mean([B[m]["apex_first"][idx[m][d]] > 0 for d in ds])) for m in B}
        out[per] = row
        print(f"\n{per} ({len(ds)} starts) — five-account book per 4 months:", flush=True)
        for key, lab in (("apex", "Apex 50K (best fixed brackets)"), ("tradeify_fixed", "Tradeify 50K Daily (best fixed)"), ("tradeify_policy", "Tradeify 50K Daily (solved policy)")):
            x = row[key]; print(f"  {lab:36}: {x['book']:+8,.0f}  P(net>0) {x['p_pos']:.0%}  p10 {x['p10']:+8,.0f} | " +
                                ", ".join(f"{m} {v:+,.0f}" for m, v in x["per_account"].items()), flush=True)
        print("  Apex P(any payout) per account: " + ", ".join(f"{m} {v:.0%}" for m, v in pay.items()), flush=True)
    (ROOT / "reports" / "a58_apex.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
