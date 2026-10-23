"""C-family 1 (decisions.md 907): large hourly moves in liquid Coinbase USD crypto — reversal (buy drops) or continuation (buy rises).

    python -m futuresres.xarb.c1_moves fetch
    python -m futuresres.xarb.c1_moves              # discovery (2024-01 -> 2025-06)
    python -m futuresres.xarb.c1_moves validate     # sealed (2025-07 -> 2026-10), once
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np

from futuresres.xarb.x1_snapshot import get
from futuresres.xarb.x3_listings import CB, candles

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "xarb" / "c1"
COST, PRIOR_SD, SEAL = 0.008, 0.02, "2025-07-01"
STABLE = {"USDT", "USDC", "DAI", "PYUSD", "EURC", "USDS", "GUSD", "PAX", "USD1", "RLUSD", "USDG", "FDUSD", "TUSD"}
RULES = [(d, th, h) for d in ("reversal", "continuation") for th in (0.05, 0.08) for h in (4, 12, 24)]


def universe() -> list[str]:
    P = [p for p in get(f"{CB}/products") if p["quote_currency"] == "USD" and p["status"] == "online" and p["base_currency"] not in STABLE]
    vol = []
    for p in P:
        try:
            s = get(f"{CB}/products/{p['id']}/stats"); vol.append((float(s.get("volume_30day") or 0) * float(s.get("last") or 0), p["id"]))
        except Exception:
            pass
        time.sleep(0.25)
    return [pid for _, pid in sorted(vol, reverse=True)[:40]]


def fetch() -> None:
    OUT.mkdir(parents=True, exist_ok=True); uf = OUT / "universe.json"
    U = json.loads(uf.read_text()) if uf.exists() else universe(); uf.write_text(json.dumps(U))
    for pid in U:
        f = OUT / f"{pid}.json"
        if f.exists():
            continue
        t = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc); end = dt.datetime(2026, 10, 22, tzinfo=dt.timezone.utc); rows = {}
        while t < end:
            for c in candles(pid, t, 3600, 300):
                rows[int(c[0])] = c
            t += dt.timedelta(hours=300)
        f.write_text(json.dumps(sorted(rows.values()))); print(pid, len(rows), flush=True)


def events(validate: bool) -> list[dict]:
    out = []
    for pid in json.loads((OUT / "universe.json").read_text()):
        f = OUT / f"{pid}.json"
        if not f.exists():
            continue
        C = json.loads(f.read_text()); t = [int(c[0]) for c in C]; o = [c[3] for c in C]; cl = [c[4] for c in C]
        idx = {x: i for i, x in enumerate(t)}
        last = {0.05: -1e18, 0.08: -1e18}
        for i in range(1, len(C) - 25):
            if t[i] - t[i - 1] != 3600:
                continue
            r = cl[i] / cl[i - 1] - 1; day = dt.datetime.fromtimestamp(t[i], dt.timezone.utc)
            if (day.isoformat() >= SEAL) != validate:
                continue
            for th in (0.05, 0.08):
                if abs(r) >= th and t[i] - last[th] >= 86400:
                    last[th] = t[i]; e = idx.get(t[i] + 3600)
                    if e is None:
                        continue
                    for h in (4, 12, 24):
                        x = idx.get(t[i] + 3600 * (h + 1))
                        if x is None:
                            continue
                        g = cl[x - 1] / o[e] - 1 if x - 1 >= e else None          # buy next hour's open, sell at the close of hour h
                        if g is None:
                            continue
                        out.append({"pid": pid, "day": day.date().isoformat(), "dir": "reversal" if r < 0 else "continuation", "th": th, "h": h,
                                    "ret": g - COST})
    return out


def run(validate: bool) -> None:
    E = events(validate); res = {}
    print(f"C1 {'sealed' if validate else 'discovery'}: event-rows {len(E)}")
    for d, th, h in RULES:
        sub = [e for e in E if e["dir"] == d and e["th"] == th and e["h"] == h]
        by = collections.defaultdict(list)
        for e in sub:
            by[e["day"]].append(e["ret"])
        x = np.array([e["ret"] for e in sub]); dm = np.array([np.mean(v) for v in by.values()])
        if len(dm) < 3:
            continue
        m = float(x.mean()); tt = float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm))))
        line = f"  {d:12} ≥{th:.0%} hold {h:2}h: n {len(x):4} days {len(dm):4} mean {m*100:+.2f}% median {np.median(x)*100:+.2f}% t {tt:+.2f}"
        key = f"{d}|{th}|{h}"
        if validate:
            rng = np.random.default_rng(907)
            pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
            post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
            res[key] = "CONFIRM" if (tt > 1.645 and pct >= 95 and m > 0 and post > 0) else ("WATCHLIST" if m > 0 else "REJECT")
            line += f" placebo {pct:.0f}th -> {res[key]}"
        else:
            res[key] = bool(m > 0 and tt > 1.96); line += "  CARRIED" if res[key] else ""
        print(line)
    (ROOT / "reports" / ("c1_validation.json" if validate else "c1_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    a = sys.argv[1:2]
    fetch() if a == ["fetch"] else run(a == ["validate"])
