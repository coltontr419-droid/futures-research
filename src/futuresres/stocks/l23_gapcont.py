"""L-families 23-25 (decisions.md 1014-1015): earnings-gap continuation — gap-up >= 4% after an outside-hours Item 2.02 8-K, open -> close vs SPY.

    python -m futuresres.stocks.l23_gapcont fetch      # EDGAR submissions (recent + older pages) -> events
    python -m futuresres.stocks.l23_gapcont [validate]
"""

from __future__ import annotations

import bisect
import collections
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

from futuresres.stocks.ai1_reads import get

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "stocks" / "l23"
COST, PRIOR_SD, SEAL, GAP = 0.001, 0.02, "2023-01", 0.04


def et(at: str) -> dt.datetime:
    t = dt.datetime.fromisoformat(at.replace("Z", "+00:00"))
    y = t.year                                                   # US DST: 2nd Sunday of March 07:00Z -> 1st Sunday of November 06:00Z
    mar = dt.datetime(y, 3, 8, 7, tzinfo=dt.timezone.utc); mar += dt.timedelta(days=(6 - mar.weekday()) % 7)
    nov = dt.datetime(y, 11, 1, 6, tzinfo=dt.timezone.utc); nov += dt.timedelta(days=(6 - nov.weekday()) % 7)
    return (t - dt.timedelta(hours=4 if mar <= t < nov else 5)).replace(tzinfo=None)


def fetch() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    syms = set(np.load(ROOT / "data" / "stocks" / "long" / "pack.npz")["syms"].tolist())
    tk = get("https://www.sec.gov/files/company_tickers.json"); cik = {v["ticker"]: v["cik_str"] for v in tk.values() if v["ticker"] in syms}
    ev = []
    for s, c in sorted(cik.items()):
        r = get(f"https://data.sec.gov/submissions/CIK{c:010d}.json")
        if not r:
            continue
        blocks = [r["filings"]["recent"]]
        for f in r["filings"].get("files", []):
            if f.get("filingTo", "") >= "2016-01-01":
                b = get(f"https://data.sec.gov/submissions/{f['name']}")
                if b:
                    blocks.append(b)
        for f in blocks:
            for form, items, at in zip(f["form"], f["items"], f["acceptanceDateTime"]):
                if form != "8-K" or "2.02" not in items:
                    continue
                t = et(at)
                if not ("2016-01-01" <= t.date().isoformat() <= "2026-10-16"):
                    continue
                hm = t.hour * 60 + t.minute
                if 570 <= hm < 960:
                    continue
                ev.append({"sym": s, "t": t.isoformat(), "after_close": hm >= 960})
    json.dump(ev, open(OUT / "events.json", "w")); print("events", len(ev))


def main(validate: bool, rule: str = "L23") -> None:
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = list(z["cal"]); sx = {s: i for i, s in enumerate(z["syms"])}
    O, A = z["O"].astype(np.float64), z["A"].astype(np.float64)
    y = json.loads((ROOT / "data" / "stocks" / "y_SPY.json").read_text())["chart"]["result"][0]; q = y["indicators"]["quote"][0]
    spy = {dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(): (o, c) for t, o, c in zip(y["timestamp"], q["open"], q["close"]) if o and c}
    res, seen, n = collections.defaultdict(list), set(), 0
    for e in json.load(open(OUT / "events.json")):
        d = e["t"][:10]; i = bisect.bisect_right(cal, d) if e["after_close"] else bisect.bisect_left(cal, d)
        if i <= 0 or i >= len(cal) or (cal[i][:7] >= SEAL) != validate or (e["sym"], i) in seen or cal[i] not in spy:
            continue
        seen.add((e["sym"], i)); j = sx[e["sym"]]
        o, c, pc = O[j, i], A[j, i], A[j, i - 1]
        if not (np.isfinite(o) and np.isfinite(c) and np.isfinite(pc)) or o <= 0 or pc <= 0:
            continue
        g = o / pc - 1
        if rule == "L23" and g >= GAP:
            r = c / o - 1 - (spy[cal[i]][1] / spy[cal[i]][0] - 1) - COST
        elif rule == "L24" and g <= -0.08:
            r = c / o - 1 - (spy[cal[i]][1] / spy[cal[i]][0] - 1) - COST
        elif rule == "L25" and g >= GAP and i + 20 < len(cal) and cal[i + 20] in spy and np.isfinite(A[j, i + 20]):
            r = A[j, i + 20] / o - 1 - (spy[cal[i + 20]][1] / spy[cal[i]][0] - 1) - 0.002
        else:
            continue
        res[cal[i][:7]].append(r); n += 1
    x = np.array([np.mean(v) for _, v in sorted(res.items())]); m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    allr = np.concatenate([np.array(v) for v in res.values()])
    s = f"{rule} {'sealed' if validate else 'discovery'}: trades {n}, months {len(x)}, excess {m*100:+.3f}%/trade-month, t {t:+.2f}; per-trade mean {allr.mean()*100:+.3f}%, win {np.mean(allr>0)*100:.0f}%"
    if validate:
        rng = np.random.default_rng(1014); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        s += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        s += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(s)


if __name__ == "__main__":
    a = sys.argv[1:2]
    rl = next((x for x in sys.argv[1:] if x.startswith("L2")), "L23")
    fetch() if a == ["fetch"] else main("validate" in sys.argv[1:], rl)
