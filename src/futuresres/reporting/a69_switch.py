"""A69 - the switch from one NKD account to five: take account #1's third payout, or hold it (decisions.md 645). No trial."""

from __future__ import annotations

import datetime as dt
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a63_firms as f
import futuresres.reporting.a67_cashpath as a67
from futuresres.reporting.a60_live import data, summary

ROOT = Path(__file__).resolve().parents[3]
MIX = ("NKD", "NKD", "NKD", "FDXM", "FDXM")
INIT = [{"phase": 1, "eq": f.START + 2_000.0, "pk": f.START + 2_000.0, "npay": 2}, None, None, None, None]


def main() -> int:
    warnings.filterwarnings("ignore"); out = {}
    cp, Pp = data("post"); P = a67.launch_paths(Pp)
    base = dict(f.FIRMS["Tradeify Select Daily"], init=INIT, init_bookpay=2)
    for window in (84, 252):
        st = np.array(cp[: len(cp) - window]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st]); mall = np.ones(len(st), bool)
        for lab, extra in (("accept", {}), ("hold until 1 new account paid", {"hold_first_until": 1}),
                           ("hold until 2 new accounts paid", {"hold_first_until": 2}), ("hold until all 4 paid", {"hold_first_until": 4}),
                           ("#1 idle (no trades) until the move", {"idle_first": True})):
            r = f.simulate(cp, P, window, MIX, dict(base, **extra))
            fm = r["moves"]
            row = {"all": summary(r, mall), "2025 starts": summary(r, m25) if m25.any() else None}
            out[f"{window} | {lab}"] = row
            a = row["all"]; b = row["2025 starts"]
            print(f"{window} sessions | {lab:31}: all starts {a['net_mean']:+8,.0f} (P>0 {a['p_pos']:.0%}, p10 {a['p10']:+,.0f})"
                  + (f" | 2025 starts {b['net_mean']:+8,.0f} ({b['p_pos']:.0%})" if b else "") + f" | moves to live {a['moves']:.2f}, cool-off days {a['cool_days']:.0f}, "
                  f"live paid ${a['paid_live']:,.0f}", flush=True)
    (ROOT / "reports" / "a69_switch.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
