"""A42 - family 146's CONFIRMs stress-tested in the account (decisions.md 525). No trial.
NKD follows ITB's 5-day sign (D551), alone and combined with the deployed dollar-week rule; ZS follows IBB's 1-day sign (D548/D552).

    python -m futuresres.reporting.a42_itb
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a27_standalone as a27
import futuresres.reporting.d136_goldwin as d136
import futuresres.reporting.d146_newseries as d146
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))


def scaled(p: str, h: int) -> dict:
    d146.load(p) if p in d146.OC + d146.CC else None
    S = d136.series(p, h); m = float(np.median([abs(v) for d, v in S.items() if DISC[0] <= d <= DISC[1]]))
    return {d: v / m for d, v in S.items()}


def rules() -> dict:
    itb, eur, ibb = scaled("ITB", 5), scaled("6E=F", 5), scaled("IBB", 1)
    combo = {d: itb.get(d, 0.0) + eur.get(d, 0.0) for d in set(itb) | set(eur)}
    return {"NKD": {"dollar-week (deployed)": eur, "ITB 5d (D551)": itb, "ITB + dollar-week": combo}, "ZS": {"IBB 1d (D552)": ibb}}


def overlay(n_random: int = 100) -> dict:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; out = {}
    for mkt, R in rules().items():
        n, rt = a23.MARKETS[mkt]
        for era in ("pre", "post"):
            (h, l, c), d = a23.market_paths(mkt, era); dd = [x.astype(object) for x in d]
            m25 = np.array([v >= dt.date(2025, 1, 1) for v in dd])[: len(dd) - 84]
            base = a23.replay(s, (h, l, c), n, rt)
            row = {"p_payout": float((base["first"] > 0).mean()), "mean_net": float(base["net"].mean())}
            if m25.any():
                row["mean_net_2025_starts"] = float(base["net"][m25].mean()); row["p_payout_2025_starts"] = float((base["first"][m25] > 0).mean())
            out[f"{mkt} {era} | plan"] = row
            print(f"{mkt} {era} plan                  : P(payout) {row['p_payout']:.0%} mean {row['mean_net']:+7,.0f}"
                  + (f" | 2025 starts {row['mean_net_2025_starts']:+7,.0f} ({row['p_payout_2025_starts']:.0%})" if m25.any() else ""), flush=True)
            for name, P in R.items():
                short = np.array([P.get(d3.prev_weekday(v), 0.0) for v in dd]) < 0
                r = a23.replay(s, a27.flip(h, l, c, short), n, rt)
                rng = np.random.default_rng(525); rnd = np.array([a23.replay(s, a27.flip(h, l, c, rng.permutation(short)), n, rt)["net"].mean() for _ in range(n_random)])
                row = {"p_payout": float((r["first"] > 0).mean()), "mean_net": float(r["net"].mean()), "short_share": float(short.mean()),
                       "random_mean": float(rnd.mean()), "beats_random_pct": float((rnd < r["net"].mean()).mean() * 100)}
                if m25.any():
                    row["mean_net_2025_starts"] = float(r["net"][m25].mean()); row["p_payout_2025_starts"] = float((r["first"][m25] > 0).mean())
                out[f"{mkt} {era} | {name}"] = row
                print(f"{mkt} {era} {name:22}: P(payout) {row['p_payout']:.0%} mean {row['mean_net']:+7,.0f} short {row['short_share']:.0%} | random "
                      f"{row['random_mean']:+7,.0f}, beats {row['beats_random_pct']:.0f}%"
                      + (f" | 2025 starts {row['mean_net_2025_starts']:+7,.0f} ({row['p_payout_2025_starts']:.0%})" if m25.any() else ""), flush=True)
    return out


def main(argv=None) -> int:
    (ROOT / "reports" / "a42_itb.json").write_text(json.dumps({"overlay": overlay()}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
