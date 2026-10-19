"""C1: calibration of executed Kalshi combos (MVE / RFQ parlays): last trade price vs result, volume-weighted, per series and price band.

    python -m futuresres.combo.c1_calib [max_pages_per_series]
"""

from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "5")
from kalshi_api import Client  # noqa: E402

SERIES = ["KXMVECROSSCATEGORY", "KXMVECROSSCATEGORY0", "KXMVECROSSCATEGORY-SHARD1", "KXMVECROSSCATEGORY0-SHARD1", "KXMVESPORTSMULTIGAMEEXTENDED"]
OUT = ROOT / "data" / "kalshi" / "combo"
BANDS = [(0, .02), (.02, .05), (.05, .10), (.10, .20), (.20, .35), (.35, .50), (.50, .65), (.65, .80), (.80, .95), (.95, 1.01)]


def main(argv) -> int:
    c = Client(); OUT.mkdir(parents=True, exist_ok=True); pages = int(argv[0]) if argv else 30
    for s in SERIES:
        f = OUT / f"{s}.jsonl"
        if f.exists():
            continue
        cur, n = None, 0
        with open(f, "w") as fh:
            for _ in range(pages):
                d = c.req("GET", f"/markets?series_ticker={s}&status=settled&limit=1000" + (f"&cursor={cur}" if cur else ""))
                for m in d.get("markets", []):
                    lp = m.get("last_price_dollars"); v = float(m.get("volume_fp") or 0)
                    if m.get("result") in ("yes", "no") and lp and v > 0:
                        legs = m.get("mve_selected_legs") or []
                        fh.write(json.dumps({"p": float(lp), "v": v, "y": m["result"] == "yes", "legs": len(legs),
                                             "cats": sorted({l["event_ticker"].split("-")[0] for l in legs})[:6], "close": m["close_time"]}) + "\n"); n += 1
                cur = d.get("cursor")
                if not cur or not d.get("markets"):
                    break
        print(s, n, "combos", flush=True)
    rows = [json.loads(l) for s in SERIES for l in open(OUT / f"{s}.jsonl")]
    print(f"\nall combos {len(rows):,}; volume {sum(r['v'] for r in rows):,.0f}")

    def table(rs, label):
        b = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0])
        for r in rs:
            for lo, hi in BANDS:
                if lo <= r["p"] < hi:
                    x = b[(lo, hi)]; x[0] += r["v"]; x[1] += r["v"] * r["y"]; x[2] += r["v"] * r["p"]; x[3] += 1
        print(f"-- {label}: {len(rs):,} combos")
        for (lo, hi), (v, yv, pv, n) in sorted(b.items()):
            print(f"   price {lo:4.2f}-{hi:4.2f}: n {n:6} vol {v:10,.0f} | avg price {pv/v:5.3f} | YES rate {yv/v:5.3f} | buyer's edge per $1 contract {yv/v - pv/v:+.3f}")
        V = sum(r['v'] for r in rs); print(f"   overall: avg price {sum(r['v']*r['p'] for r in rs)/V:.3f}, YES rate {sum(r['v']*r['y'] for r in rs)/V:.3f}, "
                                          f"seller's margin ${sum(r['v']*(r['p']-r['y']) for r in rs):,.0f} on ${sum(r['v']*r['p'] for r in rs):,.0f} of premium")
    table(rows, "all")
    sport = [r for r in rows if not any("15M" in c_ for c_ in r["cats"])]; crypto = [r for r in rows if all("15M" in c_ for c_ in r["cats"])]
    table(crypto, "crypto 15-min legs only"); table(sport, "everything else (sports etc.)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
