"""A75 - more contracts before live, and the account mix, under the adopted live plan (decisions.md 660). No trial.

    python -m futuresres.reporting.a75_sim_contracts
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import SEEDS, randomised, setup

ROOT = Path(__file__).resolve().parents[3]
LIMIT = 4
LIVE = dict(live_k={"NKD": 3.0, "FDXM": 2.0}, live_k_when="start", live_k_price=True)      # decisions.md 657
PERS = ("2021-24", "2025 starts", "2021-26", "2010-20")


def main() -> int:
    warnings.filterwarnings("ignore"); out = {}
    cp, Pp = data("post"); cq, Pq = data("pre"); P1, Q1 = launch_paths(Pp), launch_paths(Pq)
    st = np.array(cp[: len(cp) - 84]); m24 = np.array([x < dt.date(2025, 1, 1) for x in st])
    F, P = setup("50K", P1); Fq, Q = setup("50K", Q1); F.update(LIVE); Fq.update(LIVE)

    def read(o, mix):
        r = f.simulate(cp, P, 84, mix, dict(F, **o)); rq = f.simulate(cq, Q, 84, mix, dict(Fq, **o))
        x = {"2021-24": summary(r, m24), "2025 starts": summary(r, ~m24), "2021-26": summary(r, np.ones(len(st), bool)), "2010-20": summary(rq, np.ones(len(rq["net"]), bool))}
        x["zero edge 2021-26"] = float(np.mean([f.simulate(cp, randomised(P, s), 84, mix, dict(F, **o))["net"].mean() for s in SEEDS]))
        x["zero edge 2010-20"] = float(np.mean([f.simulate(cq, randomised(Q, s), 84, mix, dict(Fq, **o))["net"].mean() for s in SEEDS]))
        return x

    def show(lab, x):
        print(f"{lab:30}: " + " | ".join(f"{p} {x[p]['net_mean']:+,.0f} (med {x[p]['net_median']:+,.0f}, {x[p]['p_pos']:.0%}, p10 {x[p]['p10']:+,.0f})" for p in PERS)
              + f" | zero edge {x['zero edge 2021-26']:+,.0f} / {x['zero edge 2010-20']:+,.0f}", flush=True)

    def adopt(b_, c_):
        return bool(b_["2025 starts"]["net_mean"] > c_["2025 starts"]["net_mean"] and b_["2010-20"]["net_mean"] >= c_["2010-20"]["net_mean"] - 250
                    and b_["zero edge 2021-26"] >= c_["zero edge 2021-26"] and b_["zero edge 2010-20"] >= c_["zero edge 2010-20"]
                    and b_["2025 starts"]["p10"] >= c_["2025 starts"]["p10"] - 1000)

    MIX = f.MIXES["5: 3NKD+2FDXM"]
    base24 = float(f.simulate(cp, P, 84, MIX, F)["net"][m24].mean()); print(f"base 2021-24 {base24:+,.0f}", flush=True)
    grid = {}
    for k, where, price in itertools.product((2, 3, 4), ("eval", "funded", "both"), (False, True)):
        o = dict(sim_k={"NKD": float(min(k, LIMIT)), "FDXM": min(2 * k, LIMIT) / 2.0}, sim_k_where=where, sim_k_price=price)
        key = f"k{k}|{where}|{'price' if price else 'dollars'}"
        grid[key] = (o, float(f.simulate(cp, P, 84, MIX, dict(F, **o))["net"][m24].mean())); print(f"  {key:22}: 2021-24 {grid[key][1]:+,.0f}", flush=True)
    best = max(grid, key=lambda k: grid[k][1])
    out["part1"] = {"grid_2021_24": {k: v[1] for k, v in grid.items()}, "base": read({}, MIX), "chosen": {"key": best, **read(grid[best][0], MIX)}}
    show("base (plan's contracts)", out["part1"]["base"]); show(f"chosen {best}", out["part1"]["chosen"])
    out["part1"]["adopt"] = adopt(out["part1"]["chosen"], out["part1"]["base"]); print(f"Part 1 adopt: {out['part1']['adopt']}", flush=True)
    o1 = grid[best][0] if out["part1"]["adopt"] else {}
    mixes = ("5: NKD×5", "5: 4NKD+1FDXM", "5: 3NKD+2FDXM", "5: 2NKD+3FDXM")
    g2 = {mx: float(f.simulate(cp, P, 84, f.MIXES[mx], dict(F, **o1))["net"][m24].mean()) for mx in mixes}
    for mx, v in g2.items():
        print(f"  {mx:16}: 2021-24 {v:+,.0f}", flush=True)
    bm = max(g2, key=g2.get)
    out["part2"] = {"grid_2021_24": g2, "chosen": bm}
    if bm != "5: 3NKD+2FDXM":
        out["part2"]["base"] = read(o1, MIX); out["part2"]["chosen_read"] = read(o1, f.MIXES[bm])
        show("3 NKD + 2 FDXM", out["part2"]["base"]); show(bm, out["part2"]["chosen_read"])
        out["part2"]["adopt"] = adopt(out["part2"]["chosen_read"], out["part2"]["base"])
    else:
        out["part2"]["adopt"] = False
    print(f"Part 2: chosen {bm}; adopt {out['part2']['adopt']}", flush=True)
    (ROOT / "reports" / "a75_sim_contracts.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
