"""Kalshi liquidity-incentive markets: current order-book competition and the share a new quoter would earn (decisions.md 692).
A measurement of the present (public order books), not a backtest. Writes reports/lip_probe.json."""

from __future__ import annotations

import datetime as dt
import json
import random
import sys
from pathlib import Path

import numpy as np

import futuresres.kalshi.download as k

ROOT = Path(__file__).resolve().parents[3]


def ts(x):
    return dt.datetime.fromisoformat(x.replace("Z", "+00:00"))


def side_score(levels, target, disc, add_size, add_ticks_below_ref):
    """levels: [(price_cents, size)] best first. Our order add_size placed add_ticks_below_ref below the reference after it is set.
    Returns (our share of the side's weighted size, side reaches target with us, reference price)."""
    cum = 0; ref = None
    for p, s in levels:
        cum += s
        if cum >= target / 5:
            ref = p; break
    total = sum(s for _, s in levels)
    if ref is None:                                   # our order sets the reference
        ref_our = levels[-1][0] - 1 if levels else 50
        ref = ref_our
    ours_p = ref - add_ticks_below_ref
    w = lambda p: 1.0 if p >= ref else disc ** (ref - p)
    others = sum(s * w(p) for p, s in levels if True)
    mine = add_size * w(ours_p)
    reach = total + add_size >= target
    return mine / (others + mine) if (others + mine) > 0 else 0.0, reach, ref, ours_p


def main(n_sample: int = 300) -> int:
    P = json.load(open(ROOT / "data" / "kalshi" / "lip_active.json")); now = dt.datetime.now(dt.timezone.utc)
    P = [p for p in P if ts(p["start_date"]) <= now < ts(p["end_date"]) and (ts(p["end_date"]) - ts(p["start_date"])).total_seconds() >= 86400 * 0.5]
    random.seed(692); S = random.sample(P, min(n_sample, len(P))); rows = []
    for p in S:
        try:
            d_ = k.get(f"/markets/{p['market_ticker']}/orderbook"); ob = d_.get("orderbook_fp") or d_.get("orderbook") or {}
        except Exception:
            continue
        def lv(key):
            x = ob.get(key) or ob.get(key + "_dollars") or []
            out = []
            for it in x:
                pr, sz = it[0], it[1]
                pr = float(pr); pr = pr * 100 if pr <= 1.0 else pr
                out.append((int(round(pr)), float(sz)))
            return sorted(out, key=lambda t: -t[0])
        yes, no = lv("yes"), lv("no")
        tgt = float(p.get("target_size_fp") or 1000); disc = (p.get("discount_factor_bps") or 5000) / 1e4
        days = (ts(p["end_date"]) - ts(p["start_date"])).total_seconds() / 86400; reward_day = p["period_reward"] / 1e4 / max(days, 1)
        res = {"ticker": p["market_ticker"], "reward_day": reward_day, "target": tgt, "disc": disc,
               "yes_depth": sum(s for _, s in yes), "no_depth": sum(s for _, s in no),
               "yes_best": yes[0][0] if yes else None, "no_best": no[0][0] if no else None}
        for ticks in (0, 3, 10):
            sy, ry, refy, py = side_score(yes, tgt, disc, tgt, ticks); sn, rn, refn, pn = side_score(no, tgt, disc, tgt, ticks)
            others_reach = res["yes_depth"] >= tgt and res["no_depth"] >= tgt
            coll = tgt * (max(py, 1) + max(pn, 1)) / 100
            share = (sy + sn) / 2; earn = share * reward_day * (1.0 if (ry and rn) else 0.0)
            res[f"t{ticks}"] = {"share": share, "earn_day": earn, "collateral": coll, "our_yes_price": py, "our_no_price": pn,
                                 "book_already_qualifies": others_reach}
        rows.append(res)
    E = np.array([r["t3"]["earn_day"] for r in rows]); C = np.array([r["t3"]["collateral"] for r in rows])
    q = np.array([r["t0"]["book_already_qualifies"] for r in rows])
    print(f"sampled {len(rows)} active LIP markets; books already meeting target on both sides: {q.mean():.0%}", flush=True)
    for t in (0, 3, 10):
        e = np.array([r[f't{t}']['earn_day'] for r in rows]); c = np.array([r[f't{t}']['collateral'] for r in rows])
        print(f"  our order (target size each side) {t:2} ticks below the reference: mean share {np.mean([r[f't{t}']['share'] for r in rows]):.0%}, "
              f"earn ${e.sum():,.0f}/day over the sample for ${c.sum():,.0f} collateral (median per market ${np.median(e):.2f}/day on ${np.median(c):,.0f})", flush=True)
    (ROOT / "reports" / "lip_probe.json").write_text(json.dumps({"time": now.isoformat(), "rows": rows}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
