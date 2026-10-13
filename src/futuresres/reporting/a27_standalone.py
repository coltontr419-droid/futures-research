"""A27 - D32 as a STANDALONE strategy on its own Tradeify 50K Daily account (decisions.md 165): trade silver's London window
(03:00 -> 11:30 New York) only on the rule's days, in the rule's direction. A COMPUTATION on the confirmed rule; no trial.

    python -m futuresres.reporting.a27_standalone

Variants fixed before running (3 SIL, $3.32 a round trip each; A23 engine with skip days and fixed brackets):
  S1  D32 days only, the plan's solver brackets              S2  D32 days only, hold to 11:30, stop $1,000
  S3  D32 days only, hold to 11:30, stop $600                 B   the same days, always LONG, hold to 11:30, stop $1,000
  S4  every day, D36's direction (follow the overnight move), hold to 11:30, stop $1,000
Each on drift-removed paths (credits only skill beyond drift) and on real paths (drift added back: the era's mean window
return, as a ramp). Eras 2010-20 (contains the discovery) and 2021-26 (out of sample).
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a26_silver as a26
import futuresres.reporting.d7_london as d7
import futuresres.signals.d_london as dl

ROOT = Path(__file__).resolve().parents[3]
N, RT = 3, 3.32


def base(era: str, real: bool):
    z = np.load(a23.CACHE / f"a26_SIL_{era}.npz"); usd = np.float32(a26.notional())
    h, l, c, d = z["h"] * usd, z["l"] * usd, z["c"] * usd, z["d"].astype("datetime64[D]")
    if real:                                     # add the era's mean window return back as a ramp
        win, _ = d7.series("xagusd")
        mu = np.mean([win[x.astype(object)] for x in d if x.astype(object) in win]) / 1e4
        T = c.shape[1]; ramp = (mu * float(usd) * np.arange(1, T + 1) / T).astype(np.float32)
        h, l, c = h + ramp, l + ramp, c + ramp
    return h, l, c, d


def flip(h, l, c, short):
    return np.where(short[:, None], -l, h), np.where(short[:, None], -h, l), np.where(short[:, None], -c, c)


def run() -> dict:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; thr = dl.cells()["D32"]["median_abs_pred"]
    _, pre = d7.series("xagusd"); out = {}
    for era in a23.ERAS if hasattr(a23, "ERAS") else ("pre", "post"):
        pass
    for era in ("pre", "post"):
        out[era] = {}
        for real in (False, True):
            h, l, c, d = base(era, real)
            x = np.array([pre.get(dd.astype(object), np.nan) for dd in d])
            strong = np.abs(np.nan_to_num(x)) > thr
            short_rule = strong & (x < 0)
            short_every = np.nan_to_num(x) < 0
            V = {"S1 D32 days, plan brackets": (flip(h, l, c, short_rule), ~strong, None),
                 "S2 D32 days, hold, stop $1,000": (flip(h, l, c, short_rule), ~strong, (1e9, 1000)),
                 "S3 D32 days, hold, stop $600": (flip(h, l, c, short_rule), ~strong, (1e9, 600)),
                 "B  same days, always long, hold, $1,000": ((h, l, c), ~strong, (1e9, 1000)),
                 "S4 every day, D36 direction, hold, $1,000": (flip(h, l, c, short_every), np.zeros(len(d), bool), (1e9, 1000))}
            lab = "real" if real else "drift removed"
            for name, (pp, skip, fixed) in V.items():
                r = a23.replay(s, pp, N, RT, skip=skip, fixed=fixed)
                row = {"p_payout": float((r["first"] > 0).mean()), "mean_net": float(r["net"].mean()), "median_net": float(np.median(r["net"])),
                       "p_net_positive": float((r["net"] > 0).mean()), "mean_fees": float(r["fees"].mean()), "starts": int(len(r["net"]))}
                out[era][f"{lab} | {name}"] = row
                print(f"{era} {lab:13} {name:42}: P(payout) {row['p_payout']:4.0%} mean {row['mean_net']:+7,.0f} median {row['median_net']:+7,.0f} "
                      f"P(net>0) {row['p_net_positive']:4.0%} fees {row['mean_fees']:5,.0f}", flush=True)
    (ROOT / "reports" / "a27_standalone.json").write_text(json.dumps(out, indent=1) + "\n")
    return out


if __name__ == "__main__":
    run(); sys.exit(0)
