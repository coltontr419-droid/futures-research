"""A92 (decisions.md 769): does a limit entry one tick better than the window open beat the plan's market entry (1 tick slippage)?
Minute paths from the entry (A21 caches, $ per contract), the plan's account brackets (NKD 1 contract: +$1,200 / -$1,000; FDXM 2
contracts: +$600 / -$500 a contract), random sides (zero edge) - adverse selection is about the path, not the signal. No trial.

    python -m futuresres.reporting.a92_limit_entry
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.a21_more_accounts as a21

ROOT = Path(__file__).resolve().parents[3]
SPEC = {"NKD": dict(tick=25.0, take=1200.0, stop=1000.0, rt=7.28), "FDXM": dict(tick=1.08, take=600.0, stop=500.0, rt=1.78)}


def outcome(h, l, c, take, stop, start):
    """Bracket P&L from minute `start` (relative path already shifted to the entry price); arrays are 1-D over minutes."""
    for t in range(start, len(c)):
        hit_s = l[t] <= -stop; hit_t = h[t] >= take
        if hit_s:
            return -stop                               # conservative: a stop and a take in the same minute -> the stop
        if hit_t:
            return take
    return float(c[-1])


def run_market(m, h, l, c, sides, spec):
    out = []
    for i, s in enumerate(sides):
        hh, ll, cc = (h[i], l[i], c[i]) if s > 0 else (-l[i], -h[i], -c[i])
        out.append(outcome(hh - 0, ll - 0, cc, spec["take"], spec["stop"], 0) - spec["tick"] - spec["rt"])   # 1 tick on entry
    return np.array(out)


def run_limit(m, h, l, c, sides, spec, k, fallback):
    res, fills = [], 0
    for i, s in enumerate(sides):
        hh, ll, cc = (h[i], l[i], c[i]) if s > 0 else (-l[i], -h[i], -c[i])
        tk = spec["tick"]
        f = next((t for t in range(min(k, len(cc))) if ll[t] <= -tk), None)
        if f is not None:
            fills += 1                                 # filled one tick better: the path relative to the fill price is path + tick
            res.append(outcome(hh + tk, ll + tk, cc + tk, spec["take"], spec["stop"], f + 1) - spec["rt"])
        elif fallback:                                 # market entry at minute k, paying a tick, path re-based to the price then
            b = cc[k - 1]
            res.append(outcome(hh - b, ll - b, cc - b, spec["take"], spec["stop"], k) - tk - spec["rt"])
        else:
            res.append(0.0)
    return np.array(res), fills / len(sides)


def main() -> int:
    out = {}
    for m in ("NKD", "FDXM"):
        spec = SPEC[m]
        for era in ("post", "pre"):
            h, l, c, d = a21.paths("DAX" if m == "FDXM" else "NKD", era)
            h, l, c = np.asarray(h, float), np.asarray(l, float), np.asarray(c, float)
            rng = np.random.default_rng(769); sides = rng.choice((-1, 1), len(c))
            base = run_market(m, h, l, c, sides, spec); r = {"market_entry": float(base.mean()), "n": len(c)}
            for k in (1, 5, 15, 30):
                a, fr = run_limit(m, h, l, c, sides, spec, k, False); b, _ = run_limit(m, h, l, c, sides, spec, k, True)
                r[f"limit_k{k}"] = {"fill_rate": fr, "skip_if_unfilled": float(a.mean()), "else_market": float(b.mean())}
            out[f"{m}_{era}"] = r
            print(f"{m} {era} (n {len(c)}): market entry {r['market_entry']:+7.1f} $/ticket | " + " | ".join(
                f"k{k}: fill {r[f'limit_k{k}']['fill_rate']:.0%} skip {r[f'limit_k{k}']['skip_if_unfilled']:+6.1f} else-mkt {r[f'limit_k{k}']['else_market']:+6.1f}"
                for k in (1, 5, 15, 30)), flush=True)
    (ROOT / "reports" / "a92_limit_entry.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
