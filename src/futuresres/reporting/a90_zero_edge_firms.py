"""A90 (decisions.md 763): zero-edge value of each prop firm's account game — sides randomised per session (6 seeds), each firm's
A63 rules and natural mix, mean net per 84-session run on 2021-26 and 2010-20 paths. If several firms are positive with no edge, the
structural play scales across firms (Tradeify alone caps at 5 accounts). Fees are A63's stored fees unless overridden (FEES).

    python -m futuresres.reporting.a90_zero_edge_firms [firm ...]
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data
from futuresres.reporting.a73_100k_live import SEEDS, randomised

ROOT = Path(__file__).resolve().parents[3]
FEES = {"Tradeify Select Daily": 116.0}          # current price (§719); others: A63's stored fees
MIX = {"Tradeify Select Daily": "5: 3NKD+2FDXM", "MFF Rapid EOD": "3: NKD×3", "TPT PRO": "5: no Eurex (NKD×3, MNQ, MGC)",
       "Lucid Daily": "5: no Eurex (NKD×3, MNQ, MGC)", "Phidias Fundamental": "5: no Eurex (NKD×3, MNQ, MGC)",
       "Phidias Premium": "5: no Eurex (NKD×3, MNQ, MGC)"}


def main(argv) -> int:
    warnings.filterwarnings("ignore"); out = {}
    cp, Pp = data("post"); cq, Pq = data("pre")
    for firm in (argv or list(MIX)):
        t0 = time.time(); F = dict(f.FIRMS[firm], fee=FEES.get(firm, f.FIRMS[firm]["fee"])); mix = f.MIXES[MIX[firm]]
        r = {}
        for lab, c, P in (("2021-26", cp, Pp), ("2010-20", cq, Pq)):
            nets, fees_ = [], []
            for s in SEEDS:
                sim = f.simulate(c, randomised(P, s), 84, mix, F)
                nets.append(float(np.mean(sim["net"]))); fees_.append(float(np.mean(sim.get("fees", [0]))))
            r[lab] = {"zero_edge_mean_net": float(np.mean(nets)), "seed_sd": float(np.std(nets)), "fees_paid": float(np.mean(fees_))}
        out[firm] = {"fee": F["fee"], "mix": MIX[firm], **r}
        print(f"{firm:22} fee ${F['fee']:5.0f} {MIX[firm]:32} zero edge 2021-26 {r['2021-26']['zero_edge_mean_net']:+8,.0f} "
              f"(fees {r['2021-26']['fees_paid']:,.0f}) | 2010-20 {r['2010-20']['zero_edge_mean_net']:+8,.0f} [{time.time()-t0:.0f}s]", flush=True)
    p = ROOT / "reports" / "a90_zero_edge_firms.json"
    old = json.loads(p.read_text()) if p.exists() else {}
    old.update(out); p.write_text(json.dumps(old, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
