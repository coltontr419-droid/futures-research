"""A54 - Tradeify's Growth 50K for the two rule accounts (decisions.md 608). No trial."""

from __future__ import annotations

import datetime as dt
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a27_standalone as a27
import futuresres.reporting.a43_scale as a43

ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    warnings.filterwarnings("ignore"); R = a43.masks(); out = {}
    specs = {"50K Daily": a23.specs()["50K Daily"],
             "Growth f_dd 20": a23.Spec("Growth 50K a", 50_000, 145.0, 30, 20, 1.0, 20, 15, 12, flex_thr=150, e_daily=12, cap_usd=1500.0),
             "Growth f_dd 30": a23.Spec("Growth 50K b", 50_000, 145.0, 30, 20, 1.0, 30, 15, 12, flex_thr=150, e_daily=12, cap_usd=1500.0)}
    for mkt, n in (("NKD", 1), ("FDXM", 2)):
        rt = a23.MARKETS[mkt][1]
        (h, l, c), d = a23.market_paths(mkt, "post"); dd = [x.astype(object) for x in d]
        pp = a27.flip(h, l, c, np.array([R[mkt](v) for v in dd])); st = np.array(dd[: len(dd) - 84]); m25 = st >= dt.date(2025, 1, 1)
        for name, s in specs.items():
            r = a23.replay(s, pp, n, rt)
            row = {"all": float(r["net"].mean()), "p_all": float((r["first"] > 0).mean()), "m25": float(r["net"][m25].mean()), "p25": float((r["first"][m25] > 0).mean())}
            out[f"{mkt} | {name}"] = row
            print(f"{mkt} {name:15}: post-2021 {row['all']:+7,.0f} ({row['p_all']:.0%}) | 2025 starts {row['m25']:+7,.0f} ({row['p25']:.0%})", flush=True)
    (ROOT / "reports" / "a54_growth.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
