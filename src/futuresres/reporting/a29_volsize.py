"""A29 - contracts sized to a volatility forecast (decisions.md 257). A COMPUTATION; zero edge; no trial.

    python -m futuresres.reporting.a29_volsize --run ERA       (every variant x market; per-start nets cached)
    python -m futuresres.reporting.a29_volsize --book          (five-account books per variant)

Per session: R = the window's per-contract range, F = mean R over the previous 20 sessions, reference = median F over the previous
250. plan: n fixed. V1: n x ref / F, clip [1, 2n]. V2: the same, clip [1, n]. V3: n x F / ref, clip [1, 2n]. Before 270 sessions
of history: n.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23

ROOT = Path(__file__).resolve().parents[3]
VARIANTS = ("plan", "V1", "V2", "V3")


def nvec(h, l, n: int, variant: str) -> np.ndarray:
    R = (np.max(h, axis=1) - np.min(l, axis=1)).astype(np.float64); S = len(R)
    out = np.full(S, n, np.int64)
    if variant == "plan":
        return out
    F = np.full(S, np.nan)
    for d in range(20, S):
        F[d] = R[d - 20:d].mean()
    for d in range(270, S):
        ref = np.median(F[d - 250:d])
        x = ref / F[d] if variant in ("V1", "V2") else F[d] / ref
        out[d] = int(np.clip(np.rint(n * x), 1, n if variant == "V2" else 2 * n))
    return out


def run(era: str) -> None:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; res = {}
    for m in a23.MARKETS:
        (h, l, c), d = a23.market_paths(m, era)
        n, rt = a23.MARKETS[m]
        for v in VARIANTS:
            t0 = time.time(); nv = nvec(h, l, n, v)
            r = a23.replay(s, (h, l, c), n, rt, nvec=nv)
            res[f"{m}|{v}"] = {"date": d[r["start"]].astype(str).tolist(), "net": r["net"].round(2).tolist(),
                               "first": r["first"].tolist(), "fees": r["fees"].round(2).tolist()}
            print(f"{era} {m:4} {v:4} contracts mean {nv.mean():5.2f} (min {nv.min()}, max {nv.max()}): P(payout) {(r['first'] > 0).mean():.0%} "
                  f"mean net {r['net'].mean():+7,.0f} P(net>0) {(r['net'] > 0).mean():.0%} fees {r['fees'].mean():5,.0f} ({time.time() - t0:.0f}s)", flush=True)
        del h, l, c
    (a23.CACHE / f"a29_replay_{era}.json").write_text(json.dumps(res))


def book() -> dict:
    out = {}
    for era in ("pre", "post"):
        R = json.loads((a23.CACHE / f"a29_replay_{era}.json").read_text()); out[era] = {}
        five = ("MNQ", "MGC", "MCL", "NKD", "FDXM")
        common = None
        for k, r in R.items():
            if k.split("|")[0] in five:
                common = set(r["date"]) if common is None else common & set(r["date"])
        common = sorted(common); print(f"== {era}: {len(common)} starts {common[0]} -> {common[-1]}", flush=True)
        for v in VARIANTS:
            net = 0; fees = 0; pays = 0
            for m in five:
                r = R[f"{m}|{v}"]; ix = {dd: i for i, dd in enumerate(r["date"])}; ii = [ix[dd] for dd in common]
                net = net + np.array(r["net"])[ii]; fees = fees + np.array(r["fees"])[ii]; pays = pays + (np.array(r["first"])[ii] > 0)
            row = {"mean_net": float(net.mean()), "median_net": float(np.median(net)), "p_net_positive": float((net > 0).mean()),
                   "net_p10": float(np.quantile(net, 0.1)), "mean_fees": float(fees.mean()), "streams_paying": float(pays.mean())}
            out[era][v] = row
            print(f"   {v:4}: mean {row['mean_net']:+8,.0f} median {row['median_net']:+8,.0f} P(net>0) {row['p_net_positive']:.0%} "
                  f"p10 {row['net_p10']:+8,.0f} fees {row['mean_fees']:6,.0f} paying {row['streams_paying']:.2f}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--run"); ap.add_argument("--book", action="store_true")
    a = ap.parse_args(argv)
    if a.run:
        run(a.run)
    if a.book:
        (ROOT / "reports" / "a29_book.json").write_text(json.dumps(book(), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
