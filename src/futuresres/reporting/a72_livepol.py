"""A72 - the solved live-account policy alone, the evaluation and funded policy unchanged (decisions.md 651). No trial.

    python -m futuresres.reporting.a72_livepol
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a71_realgame import F0, MIX, solve_live

ROOT = Path(__file__).resolve().parents[3]
PERS = ("2021-24", "2025 starts", "2021-26", "2010-20")


def main() -> int:
    warnings.filterwarnings("ignore"); out = {}
    cp, Pp = data("post"); cq, Pq = data("pre"); P1, Q1 = launch_paths(Pp), launch_paths(Pq)
    st = np.array(cp[: len(cp) - 84]); m24 = np.array([x < dt.date(2025, 1, 1) for x in st]); mall = np.ones(len(st), bool)
    s = a23.specs()["50K Daily"]

    def read(F):
        r = f.simulate(cp, P1, 84, MIX, F); rq = f.simulate(cq, Q1, 84, MIX, F)
        return {"2021-24": summary(r, m24), "2025 starts": summary(r, ~m24), "2021-26": summary(r, mall), "2010-20": summary(rq, np.ones(len(rq["net"]), bool))}

    out["current"] = read(F0)
    for H in (84, 42, 21):
        lp = {m: solve_live(s, float(P1[m][3]), H)[:2] for m in sorted(set(MIX))}
        out[f"live solved H{H}"] = read(dict(F0, live_pol=lp))
    for k, x in out.items():
        print(f"{k:18}: " + " | ".join(f"{p} {x[p]['net_mean']:+,.0f} ({x[p]['p_pos']:.0%}, p10 {x[p]['p10']:+,.0f}; live ${x[p]['paid_live']:,.0f})" for p in PERS), flush=True)
    c_, b_ = out["current"], out["live solved H84"]
    out["adopt"] = bool(b_["2025 starts"]["net_mean"] > c_["2025 starts"]["net_mean"] and b_["2010-20"]["net_mean"] > c_["2010-20"]["net_mean"]
                        and b_["2025 starts"]["p10"] >= c_["2025 starts"]["p10"] - 1000)
    print(f"adopt (decisions.md 651): {out['adopt']}", flush=True)
    (ROOT / "reports" / "a72_livepol.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
