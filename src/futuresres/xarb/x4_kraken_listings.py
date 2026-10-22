"""X4 (decisions.md 849): Kraken new listings of assets already on Coinbase — hedged gap at Kraken's open (mirror of X3 / §844).

    python -m futuresres.xarb.x4_kraken_listings
"""

from __future__ import annotations

import datetime as dt
import json
import statistics as st
import time
from pathlib import Path

from futuresres.xarb.x1_snapshot import get
from futuresres.xarb.x3_listings import CB, FEES, candles, kraken_minutes

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "data" / "xarb" / "x4"


def listings() -> list[dict]:
    DIR.mkdir(parents=True, exist_ok=True); f = DIR / "listings.json"
    if f.exists():
        return json.loads(f.read_text())
    pairs = get("https://api.kraken.com/0/public/AssetPairs")["result"]
    cb = {p["base_currency"]: p["id"] for p in get(f"{CB}/products") if p["quote_currency"] == "USD"}
    out = []; t0 = dt.datetime(2025, 3, 1, tzinfo=dt.timezone.utc).timestamp()
    for k, v in pairs.items():
        ws = v.get("wsname", "")
        if not ws.endswith("/USD"):
            continue
        base = ws.split("/")[0].replace("XBT", "BTC").replace("XDG", "DOGE")
        if base not in cb:
            continue
        time.sleep(1.1)
        try:
            r = get(f"https://api.kraken.com/0/public/Trades?pair={k}&since=0&count=1")["result"]
            tr = next(x for kk, x in r.items() if kk != "last")
            first = float(tr[0][2]) if tr else None
        except Exception:
            first = None
        if first and first > t0:
            out.append({"pair": k, "base": base, "cb": cb[base], "first": int(first)})
    f.write_text(json.dumps(out)); print("Kraken listings since 2025-03 also on Coinbase:", len(out), flush=True); return out


def main() -> None:
    rows = []
    for L in listings():
        t_open = L["first"]; K = kraken_minutes(L["base"], t_open, t_open + 1800)
        c = {int(x[0]): x for x in candles(L["cb"], dt.datetime.fromtimestamp(t_open - 60, dt.timezone.utc), 60, 40)}
        cap = 0.0; g_ = []
        for m, (kv, kusd) in K.items():
            x = c.get(m)
            if not x or x[5] <= 0:
                continue
            g = kv / x[4] - 1 - FEES; g_.append(g)          # sell on Kraken at its open, buy the same on Coinbase
            if g > 0:
                cap += min(0.1 * kusd, 0.1 * x[4] * x[5]) * g
        if g_:
            rows.append({**L, "minutes": len(g_), "median_gap": st.median(g_), "max_gap": max(g_), "capturable_usd": cap})
            print(f"{L['base']:8} {dt.datetime.fromtimestamp(t_open, dt.timezone.utc):%Y-%m-%d %H:%M}: minutes {len(g_):2}, median {st.median(g_)*100:+.1f}%, "
                  f"max {max(g_)*100:+.1f}%, capturable ${cap:,.0f}", flush=True)
    for half, lo, hi in (("to 2025-12", 0, dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp()), ("2026", dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp(), 9e12)):
        q = [r for r in rows if lo <= r["first"] < hi]
        if q:
            months = max((max(r["first"] for r in q) - min(r["first"] for r in q)) / 86400 / 30.4, 1)
            print(f"{half}: listings {len(q)}, capturable ${sum(r['capturable_usd'] for r in q):,.0f} = ${sum(r['capturable_usd'] for r in q) / months:,.0f}/month")
    (ROOT / "reports" / "x4_kraken_listings.json").write_text(json.dumps(rows, indent=0))


if __name__ == "__main__":
    main()
