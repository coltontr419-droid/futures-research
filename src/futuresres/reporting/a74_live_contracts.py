"""A74 - more contracts on live accounts (decisions.md 655). No trial.

    python -m futuresres.reporting.a74_live_contracts
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
from futuresres.reporting.a71_realgame import MIX
from futuresres.reporting.a73_100k_live import SEEDS, randomised, setup

ROOT = Path(__file__).resolve().parents[3]
LIMIT = 4                                                          # assumed 50K contract limit (minis), decisions.md 655


def main() -> int:
    warnings.filterwarnings("ignore"); out = {"grid_2021_24": {}}
    cp, Pp = data("post"); cq, Pq = data("pre"); P1, Q1 = launch_paths(Pp), launch_paths(Pq)
    st = np.array(cp[: len(cp) - 84]); m24 = np.array([x < dt.date(2025, 1, 1) for x in st])
    F, P = setup("50K", P1); Fq, Q = setup("50K", Q1)

    def opts(k, when, price):
        return {} if k == 1 else dict(live_k={"NKD": float(min(k, LIMIT)), "FDXM": min(2 * k, LIMIT) / 2.0}, live_k_when=when, live_k_price=price)

    def read(o):
        r = f.simulate(cp, P, 84, MIX, dict(F, **o)); rq = f.simulate(cq, Q, 84, MIX, dict(Fq, **o))
        x = {"2021-24": summary(r, m24), "2025 starts": summary(r, ~m24), "2021-26": summary(r, np.ones(len(st), bool)), "2010-20": summary(rq, np.ones(len(rq["net"]), bool))}
        x["zero edge 2021-26"] = float(np.mean([f.simulate(cp, randomised(P, s), 84, MIX, dict(F, **o))["net"].mean() for s in SEEDS]))
        x["zero edge 2010-20"] = float(np.mean([f.simulate(cq, randomised(Q, s), 84, MIX, dict(Fq, **o))["net"].mean() for s in SEEDS]))
        return x

    base = f.simulate(cp, P, 84, MIX, F); out["k1_2021_24"] = float(base["net"][m24].mean())
    print(f"k = 1: 2021-24 {out['k1_2021_24']:+,.0f}", flush=True)
    for k, when, price in itertools.product((2, 3, 4), ("start", "locked"), (False, True)):
        r = f.simulate(cp, P, 84, MIX, dict(F, **opts(k, when, price))); key = f"k{k}|{when}|{'price' if price else 'dollars'}"
        out["grid_2021_24"][key] = float(r["net"][m24].mean()); print(f"  {key:22}: 2021-24 {out['grid_2021_24'][key]:+,.0f}", flush=True)
    best = max(out["grid_2021_24"], key=out["grid_2021_24"].get); k, when, price = best.split("|")
    out["chosen"] = {"key": best, **read(opts(int(k[1:]), when, price == "price"))}; out["k1"] = read({})
    for lab in ("k1", "chosen"):
        x = out[lab]
        print(f"{lab:6} {out['chosen']['key'] if lab == 'chosen' else '':22}: " + " | ".join(f"{p} {x[p]['net_mean']:+,.0f} (median {x[p]['net_median']:+,.0f}, "
              f"{x[p]['p_pos']:.0%}, p10 {x[p]['p10']:+,.0f})" for p in ("2021-24", "2025 starts", "2021-26", "2010-20"))
              + f" | zero edge {x['zero edge 2021-26']:+,.0f} / {x['zero edge 2010-20']:+,.0f}", flush=True)
    c_, b_ = out["k1"], out["chosen"]
    out["adopt"] = bool(b_["2025 starts"]["net_mean"] > c_["2025 starts"]["net_mean"] and b_["2010-20"]["net_mean"] >= c_["2010-20"]["net_mean"] - 250
                        and b_["zero edge 2021-26"] >= c_["zero edge 2021-26"] and b_["zero edge 2010-20"] >= c_["zero edge 2010-20"]
                        and b_["2025 starts"]["p10"] >= c_["2025 starts"]["p10"] - 1000)
    print(f"adopt (decisions.md 655): {out['adopt']}", flush=True)
    (ROOT / "reports" / "a74_live_contracts.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
