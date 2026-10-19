"""K-series family 9 (decisions.md 745): K-family 8's base-rate rule (decisions.md 720) applied to every OTHER Kalshi mention series,
pooled. Base rates are per series and per normalised word label, from EARLIER events of that series only.

    python -m futuresres.kalshi.k9_mention_all             (discovery: events closing before 2026-06-01)
    python -m futuresres.kalshi.k9_mention_all --validate  (once, sealed 2026-06-01 -> 2026-10-19)
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

from futuresres.kalshi.k1_longshot import DATA, PRIOR_SD, _q, _t, fee
from futuresres.kalshi.k8_mention import THETAS, norm, ts

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "k9_discovery.json"
CUT = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 10, 19, 23, 59, tzinfo=dt.timezone.utc)
SERIES = [s for s in json.loads((DATA / "mention_series" / "rank.json").read_text()) if s != "KXTRUMPMENTION"]


def markets():
    """Chronological (close time, series, event, word, result, early bid, early ask, early-candle volume)."""
    rows = []
    for s in SERIES:
        for f in (DATA / s).glob("*.json"):
            ev = json.loads(f.read_text())
            for m in ev.get("markets", []):
                w = norm(m.get("yes_sub_title")); r = m.get("result")
                if not w or "does not qualify" in w or r not in ("yes", "no") or not m.get("close_time"):
                    continue
                bid = ask = None; vol = 0.0
                if m.get("candles") and m.get("open_time"):
                    t0 = ts(m["open_time"]).timestamp() + 3600
                    c = next((x for x in sorted(m["candles"], key=lambda x: int(x["end_period_ts"])) if int(x["end_period_ts"]) >= t0), None)
                    if c is not None:
                        bid, ask = _q(c, "yes_bid"), _q(c, "yes_ask"); vol = float(c.get("volume_fp") or c.get("volume") or 0)
                rows.append((ts(m["close_time"]), s, ev["event"], w, r == "yes", bid, ask, vol))
    return sorted(rows, key=lambda r: (r[0], r[2]))


def trades(lo, hi):
    seen = {}                                                      # (series, word) -> [yes count, total] from EARLIER events only
    out = []; by_event = {}
    for row in markets():
        by_event.setdefault((row[0], row[1], row[2]), []).append(row)
    for (close, s, ev), group in sorted(by_event.items()):
        for _, _, _, w, yes, bid, ask, vol in group:
            k = seen.get((s, w), [0, 0])
            if k[1] >= 5 and lo <= close < hi and bid is not None and ask is not None and bid > 0 and ask < 1 and ask - bid <= 0.10:
                p = k[0] / k[1]; ey = p - ask - fee(ask); en = (1 - p) - (1 - bid) - fee(1 - bid)
                for j, th in enumerate(THETAS):
                    if ey > th and ey >= en:
                        out.append((ev, j, (1.0 if yes else 0.0) - ask - fee(ask), s, vol))
                    elif en > th:
                        out.append((ev, j, (0.0 if yes else 1.0) - (1 - bid) - fee(1 - bid), s, vol))
        for _, _, _, w, yes, _, _, _ in group:                     # update AFTER the event: no look-ahead
            k = seen.setdefault((s, w), [0, 0]); k[0] += yes; k[1] += 1
    return out


def cell(rows, j):
    by = {}; ser = {}; vol = 0.0
    for ev, jj, pnl, s, v in rows:
        if jj == j:
            by.setdefault(ev, []).append(pnl); ser[s] = ser.get(s, 0) + 1; vol += v
    x = np.array([np.mean(v) for v in by.values()])
    return {"events": len(x), "contracts": int(sum(len(v) for v in by.values())), "mean_net": float(x.mean()) if len(x) else float("nan"),
            "t": _t(x), "series": len(ser), "top_series": sorted(ser.items(), key=lambda kv: -kv[1])[:8], "early_candle_volume": vol, "per_event": x}


def scan():
    rows = trades(dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc), CUT); res = []
    for j, th in enumerate(THETAS):
        r = {"theta": th, **cell(rows, j)}; r.pop("per_event"); r["carried"] = bool(r["t"] > 1.96 and r["mean_net"] > 0); res.append(r)
        print(f"  theta {th*100:.0f}c: events {r['events']} markets {r['contracts']} series {r['series']} net {r['mean_net']*100:+.2f}c t {r['t']:+.2f}"
              f"{'  CARRIED' if r['carried'] else ''} | top series {r['top_series'][:4]}", flush=True)
    OUT.write_text(json.dumps({"cut": str(CUT), "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}, indent=1) + "\n")


def validate():
    rows = trades(CUT, END); rng = np.random.default_rng(745); out = []
    for r in json.loads(OUT.read_text())["carried"]:
        j = THETAS.index(r["theta"]); st = cell(rows, j); x = st.pop("per_event"); n = len(x); m = st["mean_net"]
        pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m).mean() * 100)
        post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n) if n > 2 else float("nan")
        dec = "CONFIRM" if (st["t"] > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT")
        out.append({"theta": r["theta"], **st, "placebo_pct": pct, "posterior_zero_prior": post0, "decision": dec})
        print(f"  sealed theta {r['theta']*100:.0f}c: events {n} markets {st['contracts']} net {m*100:+.2f}c t {st['t']:+.2f} placebo {pct:.0f}% "
              f"posterior {post0*100:+.2f}c -> {dec} | early-candle volume {st['early_candle_volume']:,.0f}", flush=True)
    (ROOT / "reports" / "k9_validation.json").write_text(json.dumps(out, indent=1, default=str) + "\n")


if __name__ == "__main__":
    validate() if "--validate" in sys.argv else scan()
