"""A64 - Tradeify 100K / 150K Select Daily under the live rules (decisions.md 632). No trial."""

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

ROOT = Path(__file__).resolve().parents[3]
SIZES = {"50K": ("50K Daily", 1.0, 2_000.0), "100K": ("100K Daily", 1.5, 3_000.0), "150K": ("150K Daily", 2.25, 4_500.0)}


def scaled(P: dict, spec) -> dict:
    out = {}
    for m, (h, l, c, cost, has) in P.items():
        n50 = a23.MARKETS[m][0]; n = a23.contracts(m, spec); k = np.float32(n / n50)
        out[m] = (h * k, l * k, c * k, cost * float(n / n50), has)
    return out


def main() -> int:
    warnings.filterwarnings("ignore"); out = {}
    cp, Pp = data("post"); cq, Pq = data("pre"); st = np.array(cp[: len(cp) - 84]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st])
    for size, (name, k, ldd) in SIZES.items():
        spec = a23.specs()[name]
        F = dict(f.FIRMS["Tradeify Select Daily"], fee=spec.fee, spec=spec, dd=spec.dd * 100.0, target=spec.target * 100.0,
                 payout=("cap", spec.f_dd * 100.0, 0.0, spec.cap_usd), live_dd=ldd, k=k, cons=spec.cons, lock=f.START)        # balances are kept relative to a 50,000 base for every size
        Ps, Qs = scaled(Pp, spec), scaled(Pq, spec)
        for mix in ("5: 3NKD+2FDXM", "5: now"):
            r = f.simulate(cp, Ps, 84, f.MIXES[mix], F); rq = f.simulate(cq, Qs, 84, f.MIXES[mix], F)
            a, b, c = summary(r, m25), summary(r, np.ones(len(st), bool)), summary(rq, np.ones(len(rq["net"]), bool))
            out[f"{size} | {mix}"] = {"2025 starts": a, "2021-26": b, "2010-20": c}
            print(f"5 x {size:4} | {mix:14}: 2025 {a['net_mean']:+8,.0f} ({a['p_pos']:.0%}, p10 {a['p10']:+,.0f}) | 2021-26 {b['net_mean']:+8,.0f} ({b['p_pos']:.0%}, p10 "
                  f"{b['p10']:+,.0f}) | 2010-20 {c['net_mean']:+8,.0f} ({c['p_pos']:.0%}) | fees {b['fees']:,.0f} sim paid {b['paid_sim']:,.0f} live paid {b['paid_live']:,.0f}", flush=True)
    (ROOT / "reports" / "a64_sizes_live.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
