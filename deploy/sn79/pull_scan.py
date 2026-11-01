"""Flow pull threshold scan (decisions.md §1207). The bots hit our quotes when near-touch order flow is one-sided (§1206), so: rule = pull our
ask while the flow feature (bid-side minus ask-side, last 5 s BEFORE the fill's second) is above +THR, pull our bid while it is below -THR.
For each feature and threshold, over our maker fills on live tapes with "of" lines: the share of bot / background fills the rule would have
blocked and the 30 s markout (ticks) of what it blocks vs keeps. Net = -(sum of blocked markouts): positive = the rule would have saved ticks.
Blocked fills are assumed simply gone (no replacement fill), so this is an upper bound on what pulling can save.

    python pull_scan.py <our uid> <tape.jsonl> [more tapes ...]
"""
import bisect
import json
import sys
from collections import defaultdict

import numpy as np

TICK, H, W = 0.01, 30, 5


def load(path, me):
    mids, of, tflow, fills = defaultdict(list), defaultdict(dict), defaultdict(lambda: defaultdict(float)), []
    for line in open(path):
        r = json.loads(line); s = r["ts"] // 1_000_000_000
        if "of" in r:
            o = of[r["book"]].setdefault(s, defaultdict(float))
            for k, v in r["of"].items():
                o[k] += v
        elif "p" in r:
            tflow[r["book"]][s] += r["q"] * (1 if r["s"] == 0 else -1)
            if r["Ma"] == me:
                fills.append(r)
        elif r.get("bid") and r.get("ask"):
            mids[r["book"]].append((r["ts"] / 1e9, (r["bid"] + r["ask"]) / 2))
    rows = []
    ratio = lambda x, y: (x - y) / (x + y) if x + y > 0 else 0.0
    for t in fills:
        b, s = t["book"], t["ts"] // 1_000_000_000
        ms = mids[b]; i = bisect.bisect_left(ms, (t["ts"] / 1e9 + H,))
        if i >= len(ms):
            continue
        maker = 1 if t["s"] == 1 else -1                    # taker sold -> we (maker) bought
        mo = maker * (ms[i][1] - t["p"]) / TICK
        g = lambda k: sum(of[b].get(s - j, {}).get(k, 0.0) for j in range(1, W + 1))
        nb, na, nb2, na2, cb, ca = (g(k) for k in ("nb", "na", "nb2", "na2", "cb", "ca"))
        tf = [tflow[b].get(s - j, 0.0) for j in range(1, W + 1)]
        gross = sum(abs(x) for x in tf)
        feats = {"near": ratio(nb2, na2), "new": ratio(nb, na), "net": ratio(nb - cb, na - ca), "cancel": ratio(ca, cb),
                 "taker": sum(tf) / gross if gross else 0.0}
        feats["near+taker"] = (feats["near"] + feats["taker"]) / 2
        exposed = -maker                                    # our ask (maker sold, taker bought) is exposed to + (bid-side) flow
        bot = t["Ta"] is not None and t["Ta"] >= 0
        rows.append((bot, mo, t["q"], {k: exposed * v for k, v in feats.items()}))
    return rows


def main():
    me = int(sys.argv[1]); rows = []
    for p in sys.argv[2:]:
        r = load(p, me); rows += r; print(f"{p}: {len(r)} fills")
    bot = np.array([r[0] for r in rows]); mo = np.array([r[1] for r in rows])
    print(f"all {len(rows)} fills: bot {bot.mean():.0%} (mean {mo[bot].mean():+.2f}), background mean {mo[~bot].mean():+.2f}; total {mo.sum():+.0f} ticks")
    for k in rows[0][3]:
        f = np.array([r[3][k] for r in rows])
        print(f"== {k}: signed toward the exposed side, bot mean {f[bot].mean():+.3f} vs background {f[~bot].mean():+.3f}")
        for thr in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
            blk = f > thr
            if blk.sum() < 30:
                continue
            print(f"   thr {thr:.1f}: blocks {blk.mean():5.1%} of fills | bot {blk[bot].mean():5.1%}  background {blk[~bot].mean():5.1%} | "
                  f"blocked mean {mo[blk].mean():+.2f}  kept mean {mo[~blk].mean():+.2f} | net saved {-mo[blk].sum():+6.0f} ticks")


if __name__ == "__main__":
    main()
