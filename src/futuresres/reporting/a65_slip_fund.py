"""A65 - slippage on the NKD / FDXM book, and funded-stage brackets under the live rules (decisions.md 634). No trial."""

from __future__ import annotations

import datetime as dt
import itertools
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary

ROOT = Path(__file__).resolve().parents[3]
TICK = {"NKD": 25.0, "FDXM": 5.80, "MNQ": 0.50, "MGC": 1.0, "MCL": 1.0}
MIX = f.MIXES["5: 3NKD+2FDXM"]; F0 = f.FIRMS["Tradeify Select Daily"]


def slipped(P: dict, ticks: int) -> dict:
    out = {}
    for m, (h, l, c, cost, has) in P.items():
        out[m] = (h, l, c, cost + 2 * ticks * TICK[m] * a23.MARKETS[m][0], has)
    return out


def read(cp, P, cq, Q, F):
    st = np.array(cp[: len(cp) - 84]); m24 = np.array([x < dt.date(2025, 1, 1) for x in st])
    r = f.simulate(cp, P, 84, MIX, F); rq = f.simulate(cq, Q, 84, MIX, F)
    return {"2021-24": float(r["net"][m24].mean()), "2025 starts": summary(r, ~m24), "2021-26": summary(r, np.ones(len(st), bool)),
            "2010-20": summary(rq, np.ones(len(rq["net"]), bool))}


def show(lab, x):
    a, b, c = x["2025 starts"], x["2021-26"], x["2010-20"]
    print(f"{lab:32}: 2021-24 {x['2021-24']:+8,.0f} | 2025 {a['net_mean']:+8,.0f} ({a['p_pos']:.0%}, p10 {a['p10']:+,.0f}) | 2021-26 {b['net_mean']:+8,.0f} "
          f"({b['p_pos']:.0%}) | 2010-20 {c['net_mean']:+8,.0f} ({c['p_pos']:.0%})", flush=True)


def main() -> int:
    warnings.filterwarnings("ignore"); out = {}
    cp, Pp = data("post"); cq, Pq = data("pre")
    print("Part 1 - slippage (ticks a side)", flush=True)
    for t in (0, 1, 2):
        x = read(cp, slipped(Pp, t), cq, slipped(Pq, t), F0); out[f"slip {t}"] = x; show(f"{t} tick(s)", x)
    print("Part 2 - funded brackets (take x, stop x), 1 tick of slippage", flush=True)
    P1, Q1 = slipped(Pp, 1), slipped(Pq, 1); grid = {}
    for kw, kl in itertools.product((0.75, 1.0, 1.25, 1.5), repeat=2):
        st = np.array(cp[: len(cp) - 84]); m24 = np.array([x < dt.date(2025, 1, 1) for x in st])
        r = f.simulate(cp, P1, 84, MIX, dict(F0, fscale=(kw, kl))); grid[(kw, kl)] = float(r["net"][m24].mean())
        print(f"  funded x({kw}, {kl}): 2021-24 {grid[(kw, kl)]:+8,.0f}", flush=True)
    best = max(grid, key=grid.get); out["grid_2021_24"] = {f"{k[0]}|{k[1]}": v for k, v in grid.items()}
    x = read(cp, P1, cq, Q1, dict(F0, fscale=best)); out["chosen"] = {"scale": list(best), **x}
    show(f"chosen {best}", x); show("baseline (1, 1)", out["slip 1"])
    (ROOT / "reports" / "a65_slip_fund.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
