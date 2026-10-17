"""A79 forward measurement (decisions.md 692): every 15 minutes for 3 hours, a fixed random set of active Kalshi liquidity-incentive
markets; for each, the share and $ a day that posting the target size at 1c on any side below target would earn. No orders are placed.
Appends to reports/lip_sampler.jsonl."""

from __future__ import annotations

import datetime as dt
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import futuresres.kalshi.download as k

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "lip_sampler.jsonl"


def ts(x):
    return dt.datetime.fromisoformat(x.replace("Z", "+00:00"))


def programmes():
    out, cur = [], None
    for _ in range(50):
        d = k.get("/incentive_programs?status=active&limit=1000" + (f"&cursor={cur}" if cur else ""))
        ps = d.get("incentive_programs", []); out += ps; cur = d.get("next_cursor") or d.get("cursor")
        if not cur or not ps:
            break
    return out


def levels(ob, key):
    out = []
    for it in ob.get(key + "_dollars") or ob.get(key) or []:
        pr = float(it[0]); pr = pr * 100 if pr <= 1.0 else pr
        out.append((int(round(pr)), float(it[1])))
    return sorted(out, key=lambda t: -t[0])


def side(lv, target, disc, add):
    """(our share of the side's weighted size, side meets target) with our `add` contracts at 1c (add = 0: nothing posted)."""
    L = sorted(lv + ([(1, add)] if add else []), key=lambda t: -t[0])
    cum = 0; ref = None
    for p, s in L:
        cum += s
        if cum >= target / 5:
            ref = p; break
    if ref is None:
        return 0.0, False
    w = lambda p: 1.0 if p >= ref else disc ** (ref - p)
    tot = sum(s * w(p) for p, s in L); mine = add * w(1) if add else 0.0
    return (mine / tot if tot > 0 else 0.0), sum(s for _, s in L) >= target


def probe(p):
    try:
        d = k.get(f"/markets/{p['market_ticker']}/orderbook"); ob = d.get("orderbook_fp") or d.get("orderbook") or {}
    except Exception:
        return None
    yes, no = levels(ob, "yes"), levels(ob, "no")
    tgt = float(p.get("target_size_fp") or 1000); disc = (p.get("discount_factor_bps") or 5000) / 1e4
    days = (ts(p["end_date"]) - ts(p["start_date"])).total_seconds() / 86400; rday = p["period_reward"] / 1e4 / max(days, 1)
    dy, dn = sum(s for _, s in yes), sum(s for _, s in no)
    ay = tgt if dy < tgt else 0; an = tgt if dn < tgt else 0
    sy, qy = side(yes, tgt, disc, ay); sn, qn = side(no, tgt, disc, an)
    counts = qy and qn
    return {"ticker": p["market_ticker"], "reward_day": rday, "target": tgt, "yes_depth": dy, "no_depth": dn, "thin": bool(ay or an),
            "earn_day": (sy + sn) / 2 * rday if (counts and (ay or an)) else 0.0, "collateral": (ay + an) * 0.01, "share": (sy + sn) / 2}


def main(sweeps: int = 13, every_min: int = 15, n: int = 500) -> int:
    now = dt.datetime.now(dt.timezone.utc)
    P = [p for p in programmes() if ts(p["start_date"]) <= now < ts(p["end_date"]) and (ts(p["end_date"]) - ts(p["start_date"])).total_seconds() >= 43200]
    random.seed(692); S = random.sample(P, min(n, len(P)))
    print(f"{len(P)} active programmes >= 12 h; sampling {len(S)}", flush=True)
    for i in range(sweeps):
        t0 = time.time(); now = dt.datetime.now(dt.timezone.utc)
        live = [p for p in S if ts(p["end_date"]) > now]
        with ThreadPoolExecutor(8) as ex:
            rows = [r for r in ex.map(probe, live) if r]
        thin = [r for r in rows if r["thin"]]; earn = sum(r["earn_day"] for r in rows); coll = sum(r["collateral"] for r in rows)
        rec = {"time": now.isoformat(timespec="seconds"), "markets": len(rows), "thin": len(thin), "earn_day": earn, "collateral": coll, "rows": rows}
        with OUT.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"  sweep {i+1}/{sweeps} {now:%H:%M}Z: {len(rows)} markets, thin {len(thin)}, est. earnings ${earn:,.0f}/day on ${coll:,.0f} collateral", flush=True)
        if i + 1 < sweeps:
            time.sleep(max(0, every_min * 60 - (time.time() - t0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
