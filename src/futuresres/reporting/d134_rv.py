"""D-series family 134 - relative value against a sibling market, current regime (decisions.md 493)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d127_regime as d127
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d134_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
TSYM = {"MNQ": "NQ=F", "MGC": "GC=F", "CL": "CL=F", "ZS": "ZS=F", "NKD": "NKD=F", "DAX": "^GDAXI"}
PAIRS = [("MNQ", "ES=F"), ("MNQ", "RTY=F"), ("MGC", "SI=F"), ("MGC", "HG=F"), ("CL", "HO=F"), ("CL", "RB=F"), ("ZS", "ZC=F"),
         ("ZS", "ZM=F"), ("ZS", "ZL=F"), ("NKD", "ES=F"), ("DAX", "ES=F"), ("DAX", "^STOXX50E")]
FORMS = {"stretched": 1.5, "extreme": 2.0, "sign": 0.0}            # "sign": family 135 (decisions.md 497)
_C: dict = {}


def zscores(tg: str, partner: str) -> dict:
    key = (tg, partner)
    if key not in _C:
        a = dict(zip(*d127.closes(TSYM[tg]))); b = dict(zip(*d127.closes(partner)))
        ds = sorted(d for d in a if d in b and a[d] and b[d] and a[d] > 0 and b[d] > 0)
        x = np.log(np.array([a[d] for d in ds]) / np.array([b[d] for d in ds])); out = {}
        for i in range(20, len(ds)):
            w = x[i - 20:i]; sd = w.std(ddof=1)
            if sd > 0 and np.isfinite(x[i]):
                out[ds[i]] = float((x[i] - w.mean()) / sd)
        _C[key] = out
    return _C[key]


def rows(tg: str, partner: str, form: str, lo, hi):
    Z = zscores(tg, partner); Y = d111.target(tg); k = FORMS[form]; D, S, YY = [], [], []
    for d, y in Y.items():
        z = Z.get(d3.prev_weekday(d))
        if lo <= d <= hi and z is not None and abs(z) > k:
            D.append(d); S.append(np.sign(z)); YY.append(y)
    o = np.argsort(D)
    return np.array(D)[o], np.array(S)[o], np.array(YY)[o]


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for tg, partner in PAIRS:
        cost = d111.TARGETS[tg]
        for form in FORMS:
            D, S, Y = rows(tg, partner, form, *DISC)
            if len(Y) < 30:
                continue
            g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
            _, Sc, Yc = rows(tg, partner, form, *CONTEXT); cc = dirn * Sc * Yc - cost
            r = {"target": tg, "partner": partner, "form": form, "n": int(len(g)), "dir": "with stretch" if dirn == 1 else "against stretch",
                 "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()) if len(cc) else None, "context_t": _t(cc)}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
            print(f"{tg:3} vs {partner:10} {form:9}: n {r['n']:3} {r['dir']:15} net {r['net_bps']:+7.2f} t {r['t']:+5.2f}{'  CARRIED' if r['carried'] else ''} | 2010-20 "
                  f"{(r['context_net'] or float('nan')):+7.2f} t {r['context_t']:+5.2f}", flush=True)
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    return out


if __name__ == "__main__":
    scan()
