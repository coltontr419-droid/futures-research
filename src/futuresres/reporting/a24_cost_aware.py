"""A24 - a cost-aware solver: the A01 game with each product's round trip priced into the odds, and the longer horizons
re-tried with it. A COMPUTATION; zero edge; no trial. decisions.md 146.

    python -m futuresres.reporting.a24_cost_aware --run ERA        (every variant x market; per-start nets cached)
    python -m futuresres.reporting.a24_cost_aware --book           (five-account books per variant)

WHY. A01 prices a bracket +W / -L (net) as a fair coin, P(win) = L / (W + L). The gross take is W + c and the gross stop L - c
(c = contracts x round trip), so on a fair market P(win) = (L - c) / (W + L): every bracket is worse than A01 thinks, small
stops much worse. A05 (decisions.md 102) measured real odds and fitted one regime; this adds only the known cost, so it keeps
A01's regime-free coin. A19-A20 (135-136): longer horizons lost because the cost-blind solver bought tight stops.

VARIANTS, fixed before any result (the live plan's 50K Daily rules and stop menu >= $500; same rule for every market):
  plan          cost 0,  horizons 21 / 21 (the live plan)
  cost          cost c,  21 / 21
  cost 42/21    cost c,  evaluation 42, funded 21
  cost 21/63    cost c,  21 / 63
  cost 42/63    cost c,  42 / 63
Six markets at the live sizes (MNQ 4, MGC 8, MCL 10, NKD 1, FDXM 2, ZS 3), both histories, 84-day back-to-back replay from every
start date (A23's engine, which reproduces the live engine). Books: the five live markets, and soybeans in place of crude.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23

ROOT = Path(__file__).resolve().parents[3]
VARIANTS = {"plan": (False, 21, 21), "cost": (True, 21, 21), "cost 42/21": (True, 42, 21),
            "cost 21/63": (True, 21, 63), "cost 42/63": (True, 42, 63)}


def spec(market: str, variant: str) -> a23.Spec:
    use_cost, he, hf = VARIANTS[variant]
    n, rt = a23.MARKETS[market]
    return dataclasses.replace(a23.specs()["50K Daily"], cost=n * rt if use_cost else 0.0, he=he, hf=hf)


def run(era: str) -> None:
    warnings.filterwarnings("ignore")
    res = {}
    for m in a23.MARKETS:
        (h, l, c), d = a23.market_paths(m, era)
        n, rt = a23.MARKETS[m]
        for v in VARIANTS:
            t0 = time.time(); s = spec(m, v)
            r = a23.replay(s, (h, l, c), n, rt)
            res[f"{m}|{v}"] = {"date": d[r["start"]].astype(str).tolist(), "net": r["net"].round(2).tolist(),
                               "first": r["first"].tolist(), "fees": r["fees"].round(2).tolist()}
            pe = a23.policy(s)[0]; ge = a23.policy(s)[1]
            a0 = int(pe[0 - ge["B_MIN"], 0, 0])
            print(f"{era} {m:4} {v:11} cost ${s.cost:5.2f}: first eval bracket +${a0 // 100 * 100} / -${a0 % 100 * 100}; "
                  f"P(payout) {(r['first'] > 0).mean():.0%} mean net {r['net'].mean():+7,.0f} P(net>0) {(r['net'] > 0).mean():.0%} "
                  f"fees {r['fees'].mean():5,.0f} ({time.time() - t0:.0f}s)", flush=True)
        del h, l, c
    (a23.CACHE / f"a24_replay_{era}.json").write_text(json.dumps(res))


def book() -> dict:
    out = {}
    for era in ("pre", "post"):
        R = json.loads((a23.CACHE / f"a24_replay_{era}.json").read_text()); out[era] = {}
        for five in (("MNQ", "MGC", "MCL", "NKD", "FDXM"), ("MNQ", "MGC", "ZS", "NKD", "FDXM")):
            common = None
            for k, r in R.items():
                if k.split("|")[0] in five:
                    common = set(r["date"]) if common is None else common & set(r["date"])
            common = sorted(common); lab = "+".join(five); out[era][lab] = {"common_starts": len(common)}
            print(f"== {era} {lab}: {len(common)} starts {common[0]} -> {common[-1]}", flush=True)
            for v in VARIANTS:
                net = 0; fees = 0; pays = 0
                for m in five:
                    r = R[f"{m}|{v}"]; ix = {dd: i for i, dd in enumerate(r["date"])}; ii = [ix[dd] for dd in common]
                    net = net + np.array(r["net"])[ii]; fees = fees + np.array(r["fees"])[ii]
                    pays = pays + (np.array(r["first"])[ii] > 0)
                row = {"mean_net": float(net.mean()), "median_net": float(np.median(net)), "p_net_positive": float((net > 0).mean()),
                       "net_p10": float(np.quantile(net, 0.1)), "worst": float(net.min()), "mean_fees": float(fees.mean()),
                       "streams_paying": float(pays.mean())}
                out[era][lab][v] = row
                print(f"   {v:11}: mean {row['mean_net']:+8,.0f} median {row['median_net']:+8,.0f} P(net>0) {row['p_net_positive']:.0%} "
                      f"p10 {row['net_p10']:+8,.0f} worst {row['worst']:+8,.0f} fees {row['mean_fees']:6,.0f} paying {row['streams_paying']:.2f}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--run"); ap.add_argument("--book", action="store_true")
    a = ap.parse_args(argv)
    if a.run:
        run(a.run)
    if a.book:
        (ROOT / "reports" / "a24_book.json").write_text(json.dumps(book(), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
