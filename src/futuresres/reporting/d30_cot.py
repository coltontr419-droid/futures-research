"""D-series family 30 - speculator positioning sets next week's direction (decisions.md 228). Legacy COT (owned), Yahoo daily
sessions; recent-period design.

    python -m futuresres.reporting.d30_cot --scan
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import sys
import zipfile
from pathlib import Path

import numpy as np

import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d12_extreme as d12

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d30_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
CODES = {"ES": "13874A", "NQ": "209742", "RTY": "239742", "ZN": "043602", "6E": "099741", "6J": "097741", "GC": "088691", "SI": "084691",
         "HG": "085692", "CL": "067651", "NG": "023651", "ZC": "002602", "ZS": "005602", "ZW": "001602"}


def positions() -> dict:
    out = {m: {} for m in CODES}; inv = {v: k for k, v in CODES.items()}
    for f in sorted((ROOT / "data" / "cot").glob("deacot*.zip")):
        z = zipfile.ZipFile(f)
        rows = csv.reader(io.StringIO(z.read(z.namelist()[0]).decode("latin-1"))); next(rows)
        for r in rows:
            m = inv.get(r[3].strip())
            if m:
                oi = float(r[7]); net = (float(r[8]) - float(r[9])) / oi if oi > 0 else np.nan
                out[m][dt.date.fromisoformat(r[2].strip())] = net
    return out


def weekly_signals(net: dict) -> dict:
    """report Tuesday -> (flow, z or nan)."""
    ds = sorted(net); v = np.array([net[d] for d in ds]); out = {}
    for i in range(1, len(ds)):
        flow = v[i] - v[i - 1]
        z = np.nan
        if i >= 52:
            w = v[i - 52:i]; sd = w.std(ddof=1)
            if sd > 0:
                z = (v[i] - w.mean()) / sd
        out[ds[i]] = (flow, z)
    return out


def trades(S, sig, market, kind, direction, lo, hi, shuffle_rng=None):
    """(week id, session date, net bps) for sessions of the week after each report (Monday..Friday after the Tuesday + 3 days)."""
    tues = sorted(sig); vals = [sig[t] for t in tues]
    if shuffle_rng is not None:
        vals = [vals[i] for i in shuffle_rng.permutation(len(vals))]
    out = []
    for t, (flow, z) in zip(tues, vals):
        x = flow if kind == "flow" else (z if np.isfinite(z) and abs(z) > 1.5 else np.nan)
        if not np.isfinite(x) or x == 0:
            continue
        mon = t + dt.timedelta(days=6)
        for k in range(5):
            d = mon + dt.timedelta(days=k)
            if lo <= d <= hi and d in S[market]:
                out.append((t, d, float(direction * np.sign(x) * S[market][d] - d12.COST[market])))
    return out


def clustered_t(tr):
    w = {}
    for t, _, v in tr:
        w[t] = w.get(t, 0.0) + v
    x = np.array(list(w.values()))
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    S = d10.series(); P = positions(); res = []
    for m in CODES:
        sig = weekly_signals(P[m])
        for kind in ("flow", "crowding"):
            fol = trades(S, sig, m, kind, 1, *DISC)
            if len(fol) < 50:
                continue
            gross = np.mean([v for _, _, v in fol]) + d12.COST[m]; direction = 1 if gross > 0 else -1
            tr = fol if direction == 1 else trades(S, sig, m, kind, -1, *DISC)
            x = np.array([v for _, _, v in tr]); t = clustered_t(tr)
            res.append({"market": m, "kind": kind, "rule": "follow" if direction == 1 else "fade", "sessions": int(len(x)),
                        "weeks": len({a for a, _, _ in tr}), "net_bps": float(x.mean()), "t_week": t, "carried": bool(t > 1.96 and x.mean() > 0)})
    res.sort(key=lambda q: -q["t_week"])
    carried = [q for q in res if q["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for q in res[:10]:
        print(f"  {q['market']:3} {q['kind']:8} {q['rule']:6} sessions {q['sessions']:4} weeks {q['weeks']:3} net {q['net_bps']:+6.2f} bps t {q['t_week']:+5.2f}"
              f"{'  CARRIED' if q['carried'] else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
