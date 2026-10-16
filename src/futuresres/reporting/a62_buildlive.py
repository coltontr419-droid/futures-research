"""A62 - all five edge accounts live together, then build the live accounts up with smaller risk (decisions.md 628). No trial.

    python -m futuresres.reporting.a62_buildlive
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import sys
import warnings
from pathlib import Path

import numpy as np

from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a61_liveplay import MIXES, simulate

ROOT = Path(__file__).resolve().parents[3]
MIX = MIXES["3NKD+2FDXM"]
SIZES = ((300, 300), (500, 500), (800, 800), (1_200, 1_000))
CUSH = (2_000.0, 5_000.0, 10_000.0, 20_000.0)


def read(r, mask) -> dict:
    x = summary(r, mask); x["live_eq_end"] = float(r["live_eq_end"][mask].mean()); return x


def one(cp, Pp, window, **kw):
    r = simulate(cp, Pp, window, accounts=MIX, **kw); st = np.array(cp[: len(cp) - window])
    m24 = np.array([x < dt.date(2025, 1, 1) for x in st])
    return r, m24


def line(lab, x24, x25=None, xq=None):
    t = f"{lab:40}: 2021-24 cash {x24['net_mean']:+8,.0f} (P>0 {x24['p_pos']:.0%}) + live equity {x24['live_eq_end']:,.0f}"
    if x25:
        t += f" | 2025 starts {x25['net_mean']:+8,.0f} (+{x25['live_eq_end']:,.0f})"
    if xq:
        t += f" | 2010-20 {xq['net_mean']:+8,.0f} ({xq['p_pos']:.0%}, +{xq['live_eq_end']:,.0f})"
    print(t, flush=True)


def main() -> int:
    warnings.filterwarnings("ignore"); out = {}
    cp, Pp = data("post"); cq, Pq = data("pre")
    print("Stage A - all five live together? (252 sessions, A61 live play)", flush=True)
    A = {}
    for g in (None, 5):
        r, m24 = one(cp, Pp, 252, gate=g); A[g] = read(r, m24); line(f"gate {g}", A[g])
    g_best = max(A, key=lambda k: A[k]["net_mean"]); out["stageA"] = {str(k): v for k, v in A.items()}
    print(f"Stage B - live risk x cushion (gate {g_best})", flush=True)
    B = {}
    for sz, cu in itertools.product(SIZES, CUSH):
        r, m24 = one(cp, Pp, 252, gate=g_best, live_pre=sz, live_post=sz, cushion=cu); B[(sz, cu)] = read(r, m24)
        line(f"live {sz} cushion ${cu:,.0f}", B[(sz, cu)])
    best = max(B, key=lambda k: B[k]["net_mean"]); out["stageB"] = {f"{k[0]}|{k[1]}": v for k, v in B.items()}
    print(f"Chosen: gate {g_best}, live {best[0]}, cushion ${best[1]:,.0f}", flush=True)
    for lab, kw in (("A61 config", dict(gate=None)), ("chosen", dict(gate=g_best, live_pre=best[0], live_post=best[0], cushion=best[1]))):
        r, m24 = one(cp, Pp, 252, **kw); rq = simulate(cq, Pq, 252, accounts=MIX, **kw)
        out[f"252 {lab}"] = {"2021-24": read(r, m24), "2025 starts": read(r, ~m24), "2010-20": read(rq, np.ones(len(rq["net"]), bool))}
        line(f"252 {lab}", out[f"252 {lab}"]["2021-24"], out[f"252 {lab}"]["2025 starts"], out[f"252 {lab}"]["2010-20"])
        r2, _ = one(cp, Pp, 504, **kw); out[f"504 {lab}"] = read(r2, np.ones(len(r2["net"]), bool))
        line(f"504 {lab} (2021-24 starts)", out[f"504 {lab}"])
    (ROOT / "reports" / "a62_buildlive.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
