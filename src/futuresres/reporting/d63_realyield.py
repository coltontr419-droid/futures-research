"""D-series family 63 - real-yield and breakeven shocks (decisions.md 303): FRED DFII10 / T10YIE daily changes beyond 2 sigma (SD of
the previous 60) -> gold's London window and MNQ's day session on the next weekday. Recent-period design.

    python -m futuresres.reporting.d63_realyield --fetch
    python -m futuresres.reporting.d63_realyield --scan
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import sys
import urllib.request
from pathlib import Path

import numpy as np

import futuresres.reporting.d3_relay as d3
import futuresres.reporting.d8_intraday as d8

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data" / "cache"
OUT = ROOT / "reports" / "d63_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
SERIES = ("DFII10", "T10YIE")
TARGETS = {"MGC": ("london", 0.8), "MNQ": ("day", 0.5)}


def fetch() -> None:
    for s in SERIES:
        u = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}"
        (CACHE / f"fred_{s}.csv").write_bytes(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read())


def shocks(series: str) -> dict:
    """date -> (change bps, is_shock); the change is that day's, the SD from the previous 60 changes."""
    rows = [(dt.date.fromisoformat(a), float(b)) for a, b in list(csv.reader(open(CACHE / f"fred_{series}.csv")))[1:] if b not in ("", ".")]
    ds = [r[0] for r in rows]; v = np.array([r[1] for r in rows]); ch = np.diff(v) * 100; out = {}
    for i in range(60, len(ch)):
        sd = ch[i - 60:i].std(ddof=1); out[ds[i + 1]] = (float(ch[i]), bool(abs(ch[i]) > 2 * sd))
    return out


_Y: dict = {}


def target(m: str) -> dict:
    if m not in _Y:
        D, C, _, K = d8.load(m, TARGETS[m][0]); out = {}
        for i, d in enumerate(D):
            c = C[i]; f = np.where(np.isfinite(c))[0]
            if len(f) >= 200 and K[i, f[0]] == K[i, f[-1]]:
                out[d] = (c[f[-1]] / c[f[0]] - 1) * 1e4
        _Y[m] = out
    return _Y[m]


def rows(series: str, m: str, lo: dt.date, hi: dt.date, shock: bool = True):
    sh = shocks(series); D, Y, X = [], [], []
    for d, y in target(m).items():
        if not (lo <= d <= hi):
            continue
        q = sh.get(d3.prev_weekday(d))
        if q is None or q[1] != shock:
            continue
        D.append(d); Y.append(y); X.append(q[0])
    o = np.argsort(D)
    return np.array(D)[o], np.array(Y)[o], np.array(X)[o]


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for p in SERIES:
        for m, (_, cost) in TARGETS.items():
            D, Y, X = rows(p, m, *DISC); assert D.max() <= DISC[1], "discovery read sealed data"
            g = np.sign(X) * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
            r = {"predictor": p, "target": m, "n": int(len(g)), "rule": "follow" if dirn == 1 else "fade", "net_bps": float(net.mean()), "t": _t(net)}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
            print(f"{p:6} -> {m}: n {r['n']:3} {r['rule']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--fetch", action="store_true"); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.fetch:
        fetch()
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
