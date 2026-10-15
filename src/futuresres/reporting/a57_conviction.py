"""A57 - conviction sizing on the NKD account (decisions.md 619). No trial."""

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
import futuresres.reporting.d136_goldwin as d136
import futuresres.reporting.d146_newseries as d146
import futuresres.reporting.d153_asia as d153
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]


def signals():
    W = a35.weak_dollar_week("6E=F"); corn = d136.series("ZC=F", 5); d146.load("ITB"); itb = d136.series("ITB", 5); asx = d153.series("^AXJO", 1)
    def f(v):
        q = d3.prev_weekday(v); base = np.sign(W.get(q, 0.0)) or 1.0
        agree = [(-np.sign(corn.get(q, 0.0))) == base, np.sign(itb.get(q, 0.0)) == base, np.sign(asx.get(q, 0.0)) == base]
        return base, int(sum(agree))
    return f


def main() -> int:
    warnings.filterwarnings("ignore"); s = a23.specs()["50K Daily"]; rt = a23.MARKETS["NKD"][1]; f = signals(); out = {}
    rules = {"deployed (1)": lambda a: 1, "2 if >=1 agree": lambda a: 2 if a >= 1 else 1, "2 if >=2 agree": lambda a: 2 if a >= 2 else 1,
             "2 if all 3 agree": lambda a: 2 if a >= 3 else 1, "3 if all 3, 2 if 2, else 1": lambda a: 3 if a >= 3 else (2 if a >= 2 else 1)}
    for era in ("pre", "post"):
        (h, l, c), d = a23.market_paths("NKD", era); dd = [x.astype(object) for x in d]
        sg = [f(v) for v in dd]; short = np.array([b < 0 for b, _ in sg]); ag = np.array([a for _, a in sg])
        pp = a27.flip(h, l, c, short); st = np.array(dd[: len(dd) - 84]); m24 = st < dt.date(2025, 1, 1); m25 = ~m24
        for nm, rl in rules.items():
            nv = np.array([rl(a) for a in ag]); r = a23.replay(s, pp, 1, rt, nvec=nv)
            row = {"mean": float(r["net"].mean()), "p": float((r["first"] > 0).mean()), "share_up": float((nv > 1).mean())}
            if era == "post":
                row.update({"m24": float(r["net"][m24].mean()), "p24": float((r["first"][m24] > 0).mean()), "m25": float(r["net"][m25].mean()), "p25": float((r["first"][m25] > 0).mean())})
                print(f"NKD {nm:28} post: 2021-24 starts {row['m24']:+7,.0f} ({row['p24']:.0%}) | 2025 starts {row['m25']:+7,.0f} ({row['p25']:.0%}) | sized up {row['share_up']:.0%} of days", flush=True)
            else:
                print(f"NKD {nm:28} pre : {row['mean']:+7,.0f} ({row['p']:.0%}) | sized up {row['share_up']:.0%}", flush=True)
            out[f"{era} | {nm}"] = row
    (ROOT / "reports" / "a57_conviction.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
