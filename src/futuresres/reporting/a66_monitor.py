"""A66 - a health monitor for the dollar rules (decisions.md 638). No trial."""

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
NS = (20, 40, 60, 120)


def run() -> dict:
    warnings.filterwarnings("ignore"); s = a23.specs()["50K Daily"]; R = a43.masks(); out = {}
    for mkt in ("NKD", "FDXM"):
        n, rt = a23.MARKETS[mkt]
        for era in ("pre", "post"):
            (h, l, c), d = a23.market_paths(mkt, era); dd = [x.astype(object) for x in d]
            short = np.array([R[mkt](v) for v in dd]); sgn = np.where(short, -1.0, 1.0)
            signed = sgn * c[:, -1].astype(float)                        # the rule's side x the window's (drift-removed) move, $ one contract
            st = np.array(dd[: len(dd) - 84])
            rows = {"plan": a23.replay(s, (h, l, c), n, rt)["net"], "always on": a23.replay(s, a27.flip(h, l, c, short), n, rt)["net"]}
            for N in NS:
                cs = np.r_[0.0, np.cumsum(signed)]
                trail = np.array([(cs[i] - cs[i - N]) / N if i >= N else np.nan for i in range(len(signed))])
                on = np.nan_to_num(trail, nan=1.0) > 0                  # before N sessions of history: on
                rows[f"monitor N={N}"] = a23.replay(s, a27.flip(h, l, c, short & on), n, rt)["net"]
                rows[f"on share N={N}"] = float(on.mean())
            out[f"{mkt} {era}"] = {"starts": st, **rows}
    return out


def main() -> int:
    R = run(); res = {}
    keys = ["plan", "always on"] + [f"monitor N={N}" for N in NS]
    def mean(k, era, sel):
        v = []
        for mkt in ("NKD", "FDXM"):
            r = R[f"{mkt} {era}"]; m = np.array([sel(x) for x in r["starts"]]); v.append(r[k][m].mean() if m.any() else np.nan)
        return float(np.nansum(v))
    pick = {k: mean(k, "pre", lambda x: True) + mean(k, "post", lambda x: x < dt.date(2025, 1, 1)) for k in keys if k.startswith("monitor")}
    best = max(pick, key=pick.get)
    for k in keys:
        res[k] = {"2010-20": mean(k, "pre", lambda x: True), "2021-24": mean(k, "post", lambda x: x < dt.date(2025, 1, 1)),
                  "2025 starts": mean(k, "post", lambda x: x >= dt.date(2025, 1, 1))}
        print(f"{k:16}: NKD+FDXM accounts, mean net per run — 2010-20 {res[k]['2010-20']:+8,.0f} | 2021-24 {res[k]['2021-24']:+8,.0f} | 2025 starts "
              f"{res[k]['2025 starts']:+8,.0f}" + (f"  (rule on {R['NKD pre'][k.replace('monitor', 'on share')]:.0%} / {R['NKD post'][k.replace('monitor', 'on share')]:.0%} of NKD sessions pre/post)" if k.startswith("monitor") else ""), flush=True)
    print(f"chosen (2010-24 starts): {best}", flush=True); res["chosen"] = best
    (ROOT / "reports" / "a66_monitor.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
