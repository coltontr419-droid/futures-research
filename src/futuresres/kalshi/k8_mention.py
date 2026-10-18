"""K-series family 8 (decisions.md 720): base rates in Kalshi's Trump mention markets against the early quote.

    python -m futuresres.kalshi.k8_mention             (discovery: events closing before 2026-03-01)
    python -m futuresres.kalshi.k8_mention --validate  (once, sealed after)
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import numpy as np

from futuresres.kalshi.k1_longshot import DATA, _q, _t, fee

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "k8_discovery.json"
CUT = dt.datetime(2026, 3, 1, tzinfo=dt.timezone.utc)
THETAS = (0.05, 0.10, 0.15)


def ts(x):
    return dt.datetime.fromisoformat(x.replace("Z", "+00:00"))


def norm(w: str) -> str:
    return re.sub(r"\s+", " ", (w or "").lower().strip())


def markets():
    """Chronological (close time, event, word, result, early bid, early ask)."""
    rows = []
    for f in (DATA / "KXTRUMPMENTION").glob("*.json"):
        ev = json.loads(f.read_text())
        for m in ev["markets"]:
            w = norm(m.get("yes_sub_title")); r = m.get("result")
            if not w or "does not qualify" in w or r not in ("yes", "no") or not m.get("close_time"):
                continue
            bid = ask = None
            if m.get("candles") and m.get("open_time"):
                t0 = ts(m["open_time"]).timestamp() + 3600
                c = next((x for x in sorted(m["candles"], key=lambda x: int(x["end_period_ts"])) if int(x["end_period_ts"]) >= t0), None)
                if c is not None:
                    bid, ask = _q(c, "yes_bid"), _q(c, "yes_ask")
            rows.append((ts(m["close_time"]), ev["event"], w, r == "yes", bid, ask))
    return sorted(rows)


def trades(lo, hi):
    seen = {}                                                      # word -> [yes count, total] from EARLIER events only
    out = []
    by_event = {}
    for row in markets():
        by_event.setdefault((row[0], row[1]), []).append(row)
    for (close, ev), group in sorted(by_event.items()):
        for _, _, w, yes, bid, ask in group:
            k = seen.get(w, [0, 0])
            if k[1] >= 5 and lo <= close < hi and bid is not None and ask is not None and bid > 0 and ask < 1 and ask - bid <= 0.10:
                p = k[0] / k[1]; ey = p - ask - fee(ask); en = (1 - p) - (1 - bid) - fee(1 - bid)
                for j, th in enumerate(THETAS):
                    if ey > th and ey >= en:
                        out.append((ev, j, (1.0 if yes else 0.0) - ask - fee(ask)))
                    elif en > th:
                        out.append((ev, j, (0.0 if yes else 1.0) - (1 - bid) - fee(1 - bid)))
        for _, _, w, yes, _, _ in group:                           # update AFTER the event: no look-ahead
            k = seen.setdefault(w, [0, 0]); k[0] += yes; k[1] += 1
    return out


def cell(rows, j):
    by = {}
    for ev, jj, pnl in rows:
        if jj == j:
            by.setdefault(ev, []).append(pnl)
    x = np.array([np.mean(v) for v in by.values()])
    return {"events": len(x), "contracts": int(sum(len(v) for v in by.values())), "mean_net": float(x.mean()) if len(x) else float("nan"), "t": _t(x), "per_event": x}


def scan():
    rows = trades(dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc), CUT); res = []
    for j, th in enumerate(THETAS):
        r = {"theta": th, **cell(rows, j)}; r.pop("per_event"); r["carried"] = bool(r["events"] > 20 and r["t"] > 1.96 and r["mean_net"] > 0); res.append(r)
        print(f"  theta {th*100:.0f}c: events {r['events']} contracts {r['contracts']} net {r['mean_net']*100:+.2f}c t {r['t']:+.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    OUT.write_text(json.dumps({"cut": str(CUT), "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}, indent=1) + "\n")


def validate():
    rows = trades(CUT, dt.datetime(2100, 1, 1, tzinfo=dt.timezone.utc)); rng = np.random.default_rng(720); out = []
    for r in json.loads(OUT.read_text())["carried"]:
        j = THETAS.index(r["theta"]); st = cell(rows, j); x = st.pop("per_event"); n = len(x); m = st["mean_net"]
        null = np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]); pct = float((null < m).mean() * 100)
        dec = "CONFIRM" if (st["t"] > 1.645 and pct >= 95 and m > 0) else ("WATCHLIST" if m > 0 else "REJECT")
        out.append({"theta": r["theta"], **st, "placebo_pct": pct, "decision": dec})
        print(f"  sealed theta {r['theta']*100:.0f}c: events {n} net {m*100:+.2f}c t {st['t']:+.2f} placebo {pct:.0f}% -> {dec}", flush=True)
    (ROOT / "reports" / "k8_validation.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    validate() if "--validate" in sys.argv else scan()
