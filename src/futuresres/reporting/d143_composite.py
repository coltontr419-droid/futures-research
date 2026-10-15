"""D-series family 143 - composite predictors (dollar, risk, rates, commodities, grains), current regime (decisions.md 517)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d143_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
COMPOSITES = {"dollar": {"DX-Y.NYB": 1, "6E=F": -1, "6B=F": -1, "6A=F": -1, "6C=F": -1, "6S=F": -1, "6J=F": -1},
              "risk": {"ES=F": 1, "NQ=F": 1, "RTY=F": 1, "EEM": 1, "FXI": 1, "HYG": 1, "KRE": 1, "SMH": 1, "XLF": 1, "XLY": 1, "^GDAXI": 1, "^VIX": -1},
              "rates": {"ZT=F": 1, "ZN=F": 1, "ZB=F": 1, "TLT": 1},
              "commodities": {"CL=F": 1, "NG=F": 1, "RB=F": 1, "HO=F": 1, "HG=F": 1, "SI=F": 1, "GC=F": 1, "ZC=F": 1, "ZS=F": 1, "ZW=F": 1},
              "grains": {"ZC=F": 1, "ZS=F": 1, "ZM=F": 1, "ZL=F": 1, "ZW=F": 1, "SOYB": 1}}
TARGETS = d111.TARGETS
_C: dict = {}


def members(name: str, tg: str) -> dict:
    drop = set(d111.SELF[tg]) | (d111.UNIV14 if tg in ("CL", "ZS") else set())
    return {p: s for p, s in COMPOSITES[name].items() if p not in drop}


def series(name: str, h: int, tg: str) -> dict:
    key = (name, h, tg)
    if key not in _C:
        acc: dict = {}
        for p, s in members(name, tg).items():
            S = d111.predictor(p); m = float(np.median([abs(v) for d, v in S.items() if DISC[0] <= d <= DISC[1]]))
            for d, v in S.items():
                acc.setdefault(d, []).append(s * v / m)
        k = len(members(name, tg)); S = {d: float(np.mean(v)) for d, v in acc.items() if len(v) >= max(1, k // 2)}
        ds = sorted(d for d in S if d.weekday() < 5); r = np.array([S[d] for d in ds])
        _C[key] = {ds[i]: float(r[i - h + 1:i + 1].sum()) for i in range(h - 1, len(ds))}
    return _C[key]


def rows(name: str, h: int, tg: str, form: str, lo, hi, med=None):
    P = series(name, h, tg); Y = d111.target(tg)
    if med is None:
        med = float(np.median([abs(v) for d, v in P.items() if DISC[0] <= d <= DISC[1]]))
    D, S, YY = [], [], []
    for d, y in Y.items():
        x = P.get(d3.prev_weekday(d))
        if lo <= d <= hi and x and (form == "all" or abs(x) > med):
            D.append(d); S.append(np.sign(x)); YY.append(y)
    o = np.argsort(D)
    return np.array(D)[o], np.array(S)[o], np.array(YY)[o], med


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for name in COMPOSITES:
        for h in (1, 3, 5):
            for tg, cost in TARGETS.items():
                if not members(name, tg):
                    continue
                for form in ("all", "strong"):
                    D, S, Y, med = rows(name, h, tg, form, *DISC)
                    if len(Y) < 100:
                        continue
                    g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
                    _, Sc, Yc, _ = rows(name, h, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
                    r = {"predictor": name, "h": h, "target": tg, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                         "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()) if len(cc) else None, "context_t": _t(cc) if len(cc) > 2 else None}
                    r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"]); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_carries": round(0.025 * len(res), 1), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.025 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in carried:
        print(f"  {r['target']:3} <- {r['predictor']:11} {r['h']}d {r['form']:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} | 2010-20 "
              f"{(r['context_net'] or float('nan')):+6.2f} t {(r['context_t'] or float('nan')):+5.2f}", flush=True)
    return out


if __name__ == "__main__":
    scan()
