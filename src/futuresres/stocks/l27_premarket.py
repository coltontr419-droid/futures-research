"""L-family 27 (decisions.md 1040): premarket laggards vs beta x QQQ premarket move -> buy the open, sell the close (Yahoo 5-minute bars).

    python -m futuresres.stocks.l27_premarket
"""

from __future__ import annotations

import collections
import datetime as dt
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
D = ROOT / "data" / "stocks" / "l27"
COST, THR = 0.001, -0.02


def bars(sym: str) -> dict:
    r = json.loads((D / f"{sym}.json").read_text())["chart"]["result"][0]; q = r["indicators"]["quote"][0]; out = collections.defaultdict(dict)
    for t, o, c in zip(r["timestamp"], q["open"], q["close"]):
        if o is None or c is None:
            continue
        et = dt.datetime.utcfromtimestamp(t) - dt.timedelta(hours=4)   # EDT for the whole window (ends before 11-01)
        out[et.date().isoformat()][et.strftime("%H:%M")] = (o, c)
    return out


def day_points(b: dict) -> dict:
    p = {}
    for d, m in b.items():
        pre = [m[k][1] for k in sorted(m) if "04:00" <= k < "09:30"]
        if "09:30" in m and "15:55" in m:
            p[d] = {"pre": pre[-1] if pre else None, "open": m["09:30"][0], "close": m["15:55"][1]}
    return p


def main() -> None:
    uni = json.loads((D / "universe.json").read_text())
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); syms = {s: i for i, s in enumerate(z["syms"])}; cal = list(z["cal"]); A = z["A"].astype(float)
    qqq = day_points(bars("QQQ")); days = sorted(qqq)
    from futuresres.stocks.k_flows import ser
    qdates, qadj = ser("QQQ"); qd = dict(zip(qdates, qadj))                 # 60-session beta vs QQQ daily (§1040)
    ev = collections.defaultdict(list)
    for e in json.load(open(ROOT / "data" / "stocks" / "l23" / "events.json")):
        ev[e["sym"]].append(dt.datetime.fromisoformat(e["t"]))
    res = collections.defaultdict(list)
    for s in uni:
        P = day_points(bars(s)); j = syms[s]
        i0 = cal.index(days[0]) if days[0] in cal else len(cal) - 60
        w = [c for c in cal[i0 - 61:i0] if c in qd]
        if len(w) < 50:
            continue
        rs = np.diff(np.log([A[j, cal.index(c)] for c in w])); rq = np.diff(np.log([qd[c] for c in w]))
        ok = np.isfinite(rs) & np.isfinite(rq)
        beta = float(np.cov(rs[ok], rq[ok])[0, 1] / np.var(rq[ok], ddof=1))
        for k, d in enumerate(days[1:], 1):
            pd_, d0 = days[k - 1], d
            if d0 not in P or pd_ not in P or P[d0]["pre"] is None or qqq[d0]["pre"] is None:
                continue
            open_t = dt.datetime.fromisoformat(d0 + "T09:30")
            if any(open_t - dt.timedelta(hours=24) <= t <= open_t for t in ev.get(s, [])):
                continue
            sp = P[d0]["pre"] / P[pd_]["close"] - 1; qp = qqq[d0]["pre"] / qqq[pd_]["close"] - 1
            resid = sp - beta * qp
            if resid < THR:
                res[d0].append(P[d0]["close"] / P[d0]["open"] - 1 - (qqq[d0]["close"] / qqq[d0]["open"] - 1) - COST)
    x = np.array([np.mean(v) for _, v in sorted(res.items())]); n = sum(map(len, res.values()))
    if len(x) < 6:
        print("L27: too few signal days", len(x)); return
    m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    allr = np.concatenate([np.array(v) for v in res.values()])
    print(f"L27 discovery: signals {n}, days {len(x)} of {len(days)-1}, excess {m*100:+.3f}%/day, t {t:+.2f}; per-trade mean {allr.mean()*100:+.3f}%, win {np.mean(allr>0)*100:.0f}%"
          + ("  CARRIED" if m > 0 and t > 1.96 else "  not carried"))


if __name__ == "__main__":
    main()
