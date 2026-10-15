"""D-series family 174 - finer positioning: CFTC TFF and disaggregated reports, current regime (decisions.md 604)."""

from __future__ import annotations

import bisect
import csv
import datetime as dt
import io
import json
import math
import zipfile
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111

ROOT = Path(__file__).resolve().parents[3]
COT = ROOT / "data" / "cot"
OUT = ROOT / "reports" / "d174_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2011, 1, 1), dt.date(2020, 12, 31))
TFF = {"Lev_Money": "lev", "Asset_Mgr": "asset"}
PAIRS = [("tff", "209742", g, "MNQ") for g in TFF] + [("tff", "13874A", g, "MNQ") for g in TFF] + [("tff", "240741", g, "NKD") for g in TFF] + \
        [("tff", "099741", g, "DAX") for g in TFF] + [("tff", "099741", g, "NKD") for g in TFF] + [("tff", "097741", g, "NKD") for g in TFF] + \
        [("disagg", "088691", "M_Money", "MGC"), ("disagg", "067651", "M_Money", "CL"), ("disagg", "005602", "M_Money", "ZS")]
TARGETS = d111.TARGETS
_C: dict = {}


def reports(kind: str, code: str, grp: str) -> list:
    """[(release date, net/OI)] sorted."""
    key = (kind, code, grp)
    if key not in _C:
        out = {}
        for f in sorted((COT / kind).glob("*.zip")):
            z = zipfile.ZipFile(f)
            for r in csv.DictReader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding="latin-1")):
                r = {k.strip().replace(" ", "_"): (v or "").strip() for k, v in r.items() if k}
                if r.get("CFTC_Contract_Market_Code") != code:
                    continue
                try:
                    d = dt.date.fromisoformat(r["Report_Date_as_YYYY-MM-DD"]); oi = float(r["Open_Interest_All"])
                    net = float(r[f"{grp}_Positions_Long_All"]) - float(r[f"{grp}_Positions_Short_All"])
                except (KeyError, ValueError):
                    continue
                if oi > 0:
                    out[d + dt.timedelta(days=3)] = net / oi            # Tuesday positions, released Friday
        _C[key] = sorted(out.items())
    return _C[key]


def signal(p: str, kind_sig: str) -> list:
    """[(release, value)] for flow or crowding (0 inside the band)."""
    key = (p, kind_sig)
    if key not in _C:
        kind, code, grp = p.split(":"); R = reports(kind, code, grp); v = np.array([x for _, x in R]); out = []
        for i in range(52, len(R)):
            if kind_sig == "flow":
                out.append((R[i][0], float(v[i] - v[i - 1])))
            else:
                w = v[i - 52:i]; z = (v[i] - w.mean()) / (w.std() + 1e-12)
                out.append((R[i][0], float(z) if abs(z) > 1.5 else 0.0))
        _C[key] = out
    return _C[key]


def latest(S: list, d: dt.date):
    i = bisect.bisect_left([r for r, _ in S], d) - 1             # strictly before the session's date (released the Friday before)
    return S[i] if i >= 0 and (d - S[i][0]).days <= 8 else None


def group(d):
    return d.isocalendar()[:2]


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    S = signal(p, form); D, SS, Y = [], [], []
    for d, y in d111.target(tg).items():
        if not (lo <= d <= hi):
            continue
        w = latest(S, d)
        if w is None or not w[1]:
            continue
        D.append(d); SS.append(np.sign(w[1])); Y.append(y)
    o = np.argsort(D)
    return np.array(D)[o], np.array(SS)[o], np.array(Y)[o], 0.0


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for kind, code, grp, tg in PAIRS:
        p = f"{kind}:{code}:{grp}"
        for form in ("flow", "crowding"):
            D, S, Y, _ = rows(p, 1, tg, form, *DISC)
            if len(Y) < 60:
                continue
            g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - TARGETS[tg]
            G = {}
            for d, x in zip(D, net):
                G.setdefault(group(d), []).append(x)
            tw = _t(np.array([np.sum(v) for v in G.values()]))
            _, Sc, Yc, _ = rows(p, 1, tg, form, *CONTEXT); cc = dirn * Sc * Yc - TARGETS[tg]
            r = {"target": tg, "predictor": p, "h": 1, "form": form, "median_abs": 0.0, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                 "net_bps": float(net.mean()), "t": _t(net), "t_weekly": tw, "context_net": float(cc.mean()) if len(cc) else float("nan"), "context_t": _t(cc)}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0 and tw > 1.96); res.append(r)
            print(f"  {tg:3} <- {p:26} {form:8} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} (weekly {tw:+5.2f}) | 2011-20 {r['context_net']:+6.2f} "
                  f"t {r['context_t']:+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    carried = [r for r in res if r["carried"]]
    OUT.write_text(json.dumps({"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": carried}, indent=1) + "\n")
    return res


if __name__ == "__main__":
    scan()
