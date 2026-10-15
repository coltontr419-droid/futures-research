"""A45 - one account trading both dollar rules in sequence, NKD then the DAX (decisions.md 548). No trial.

    python -m futuresres.reporting.a45_twowin
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
import futuresres.reporting.a35_nkddollar as a35
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]


def pad(x: np.ndarray, T: int) -> np.ndarray:
    return np.concatenate([x, np.repeat(x[:, -1:], T - x.shape[1], axis=1)], axis=1) if x.shape[1] < T else x


def combined(era: str):
    (hn, ln, cn), dn = a23.market_paths("NKD", era); (hd, ld, cd), ddx = a23.market_paths("FDXM", era)
    T = max(cn.shape[1], cd.shape[1]); hn, ln, cn, hd, ld, cd = (pad(x, T) for x in (hn, ln, cn, hd, ld, cd))
    iN = {x.astype(object): i for i, x in enumerate(dn)}; iD = {x.astype(object): i for i, x in enumerate(ddx)}
    W = a35.weak_dollar_week("6E=F"); X = d111.predictor("DX-Y.NYB")
    H, L, C, NV, SH, DATES = [], [], [], [], [], []
    for d in sorted(set(iN) & set(iD)):
        for (h, l, c, i, nv, P) in ((hn, ln, cn, iN[d], 1, W), (hd, ld, cd, iD[d], 2, X)):
            H.append(h[i]); L.append(l[i]); C.append(c[i]); NV.append(nv); SH.append(P.get(d3.prev_weekday(d), 0.0) < 0); DATES.append(d)
    return (np.array(H, np.float32), np.array(L, np.float32), np.array(C, np.float32)), np.array(NV), np.array(SH), np.array(DATES)


def run(n_random: int = 100) -> dict:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; out = {}
    for era in ("pre", "post"):
        (h, l, c), nv, sh, dates = combined(era)
        st = dates[: len(dates) - 168]; m25 = np.array([x >= dt.date(2025, 1, 1) for x in st]); first_of_day = np.r_[True, dates[1:len(st)] != dates[:len(st) - 1]]
        sel = first_of_day                                   # starts at the NKD step of each date
        base = a23.replay(s, (h, l, c), 1, 4.0, window=168, nvec=nv)
        r = a23.replay(s, a27.flip(h, l, c, sh), 1, 4.0, window=168, nvec=nv)
        rng = np.random.default_rng(548); rnd = np.array([a23.replay(s, a27.flip(h, l, c, rng.permutation(sh)), 1, 4.0, window=168, nvec=nv)["net"] for _ in range(n_random)])
        row = {"plan_mean": float(base["net"][sel].mean()), "rule_mean": float(r["net"][sel].mean()), "rule_p_payout": float((r["first"][sel] > 0).mean()),
               "beats_random_pct": float((rnd[:, sel].mean(1) < r["net"][sel].mean()).mean() * 100)}
        k = sel & m25
        if k.any():
            row.update({"plan_2025": float(base["net"][k].mean()), "rule_2025": float(r["net"][k].mean()), "rule_p_payout_2025": float((r["first"][k] > 0).mean()),
                        "random_2025": float(rnd[:, k].mean()), "beats_random_2025_pct": float((rnd[:, k].mean(1) < r["net"][k].mean()).mean() * 100)})
        out[era] = row
        print(f"NKD+DAX {era}: plan {row['plan_mean']:+7,.0f} | rules {row['rule_mean']:+7,.0f} P {row['rule_p_payout']:.0%} beats {row['beats_random_pct']:.0f}%"
              + (f" | 2025 starts plan {row['plan_2025']:+7,.0f} rules {row['rule_2025']:+7,.0f} ({row['rule_p_payout_2025']:.0%}) random {row['random_2025']:+7,.0f} beats {row['beats_random_2025_pct']:.0f}%" if k.any() else ""), flush=True)
    return out


def main(argv=None) -> int:
    (ROOT / "reports" / "a45_twowin.json").write_text(json.dumps(run(), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
