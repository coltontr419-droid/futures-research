"""A46 - the DAX-dollar rule conditioned on 6E volume (D709) in the FDXM account (decisions.md 567). No trial.

    python -m futuresres.reporting.a46_daxvol
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
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d163_volume as d163
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]


def main(argv=None) -> int:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; n, rt = a23.MARKETS["FDXM"]
    B, _ = d163.bars("6E"); med = float(np.median([v[1] for d, v in B.items() if d163.DISC[0] <= d <= d163.DISC[1]])); X = d111.predictor("DX-Y.NYB")
    out = {}
    for era in ("pre", "post"):
        (h, l, c), d = a23.market_paths("FDXM", era); dd = [x.astype(object) for x in d]; st = np.array(dd[: len(dd) - 84]); m25 = st >= dt.date(2025, 1, 1)
        dx = np.array([X.get(d3.prev_weekday(v), 0.0) for v in dd]); b = [B.get(d3.prev_weekday(v)) for v in dd]
        hv = np.array([x is not None and x[1] > med for x in b]); e6 = np.array([x[0] if x is not None else 0.0 for x in b])
        rules = {"deployed (DX every day)": dx < 0, "high-vol 6E days use 6E, else DX": np.where(hv, e6 > 0, dx < 0),
                 "high-vol 6E days only, else long": hv & (e6 > 0)}
        for nm, short in rules.items():
            r = a23.replay(s, a27.flip(h, l, c, short), n, rt)
            rng = np.random.default_rng(567); rnd = np.array([a23.replay(s, a27.flip(h, l, c, rng.permutation(short)), n, rt)["net"] for _ in range(60)])
            row = {"mean": float(r["net"].mean()), "beats": float((rnd.mean(1) < r["net"].mean()).mean() * 100), "short": float(short.mean())}
            t = f"FDXM {era} {nm:34}: all {row['mean']:+7,.0f} (beats {row['beats']:.0f}%) short {row['short']:.0%}"
            if m25.any():
                row.update({"mean_2025": float(r["net"][m25].mean()), "p_2025": float((r["first"][m25] > 0).mean()), "beats_2025": float((rnd[:, m25].mean(1) < r["net"][m25].mean()).mean() * 100)})
                t += f" | 2025 starts {row['mean_2025']:+7,.0f} P {row['p_2025']:.0%} (beats {row['beats_2025']:.0f}%)"
            out[f"{era} | {nm}"] = row; print(t, flush=True)
    (ROOT / "reports" / "a46_daxvol.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
