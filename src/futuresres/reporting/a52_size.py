"""A52 - contract count for the two rule accounts (decisions.md 596). No trial."""

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
SIZES = {"NKD": (1, 2, 3), "FDXM": (1, 2, 3, 4)}


def main() -> int:
    warnings.filterwarnings("ignore"); s = a23.specs()["50K Daily"]; out = {}; R = a43.masks()
    for mkt, ns in SIZES.items():
        rt = a23.MARKETS[mkt][1]
        for era in ("pre", "post"):
            (h, l, c), d = a23.market_paths(mkt, era); dd = [x.astype(object) for x in d]
            short = np.array([R[mkt](v) for v in dd]); pp = a27.flip(h, l, c, short)
            st = np.array(dd[: len(dd) - 84]); m24 = st < dt.date(2025, 1, 1); m25 = ~m24
            for n in ns:
                r = a23.replay(s, pp, n, rt); rng = np.random.default_rng(596)
                rnd = np.array([a23.replay(s, a27.flip(h, l, c, rng.permutation(short)), n, rt)["net"] for _ in range(60)])
                row = {"mean": float(r["net"].mean()), "p": float((r["first"] > 0).mean()), "beats": float((rnd.mean(1) < r["net"].mean()).mean() * 100)}
                if era == "post":
                    row.update({k: float(v) for k, v in (("m24", r["net"][m24].mean()), ("p24", (r["first"][m24] > 0).mean()),
                                                           ("m25", r["net"][m25].mean()), ("p25", (r["first"][m25] > 0).mean()),
                                                           ("b25", (rnd[:, m25].mean(1) < r["net"][m25].mean()).mean() * 100))})
                    print(f"{mkt} n={n} post: 2021-24 starts {row['m24']:+7,.0f} ({row['p24']:.0%}) | 2025 starts {row['m25']:+7,.0f} ({row['p25']:.0%}, beats {row['b25']:.0f}%)", flush=True)
                else:
                    print(f"{mkt} n={n} pre : {row['mean']:+7,.0f} ({row['p']:.0%}, beats {row['beats']:.0f}%)", flush=True)
                out[f"{mkt} n={n} {era}"] = row
    (ROOT / "reports" / "a52_size.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
