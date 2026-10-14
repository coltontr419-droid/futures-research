"""A30 - skip the quietest forecast days (decisions.md 369). A COMPUTATION; zero edge; no trial.

    python -m futuresres.reporting.a30_skipquiet --run ERA
    python -m futuresres.reporting.a30_skipquiet --book
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
VARIANTS = {"plan": None, "S20": 20, "S40": 40}


def skip_mask(h, l, pct) -> np.ndarray:
    R = (np.max(h, axis=1) - np.min(l, axis=1)).astype(np.float64); S = len(R); out = np.zeros(S, bool)
    if pct is None:
        return out
    F = np.full(S, np.nan)
    for d in range(20, S):
        F[d] = R[d - 20:d].mean()
    for d in range(270, S):
        out[d] = F[d] < np.percentile(F[d - 250:d], pct)
    return out


def run(era: str) -> None:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; res = {}
    for m in a23.MARKETS:
        (h, l, c), d = a23.market_paths(m, era)
        n, rt = a23.MARKETS[m]
        for v, pct in VARIANTS.items():
            t0 = time.time(); sk = skip_mask(h, l, pct)
            r = a23.replay(s, (h, l, c), n, rt, skip=sk)
            res[f"{m}|{v}"] = {"date": d[r["start"]].astype(str).tolist(), "net": r["net"].round(2).tolist(),
                               "first": r["first"].tolist(), "fees": r["fees"].round(2).tolist()}
            print(f"{era} {m:4} {v:4} skips {sk.mean():4.0%}: P(payout) {(r['first'] > 0).mean():.0%} mean net {r['net'].mean():+7,.0f} "
                  f"P(net>0) {(r['net'] > 0).mean():.0%} fees {r['fees'].mean():5,.0f} ({time.time() - t0:.0f}s)", flush=True)
        del h, l, c
    (a23.CACHE / f"a30_replay_{era}.json").write_text(json.dumps(res))


def book() -> dict:
    out = {}
    for era in ("pre", "post"):
        R = json.loads((a23.CACHE / f"a30_replay_{era}.json").read_text()); out[era] = {}
        five = ("MNQ", "MGC", "MCL", "NKD", "FDXM")
        common = None
        for k, r in R.items():
            if k.split("|")[0] in five:
                common = set(r["date"]) if common is None else common & set(r["date"])
        common = sorted(common); print(f"== {era}: {len(common)} starts", flush=True)
        for v in VARIANTS:
            net = 0; pays = 0
            for m in five:
                r = R[f"{m}|{v}"]; ix = {dd: i for i, dd in enumerate(r["date"])}; ii = [ix[dd] for dd in common]
                net = net + np.array(r["net"])[ii]; pays = pays + (np.array(r["first"])[ii] > 0)
            row = {"mean_net": float(net.mean()), "median_net": float(np.median(net)), "p_net_positive": float((net > 0).mean()),
                   "net_p10": float(np.quantile(net, 0.1)), "streams_paying": float(pays.mean())}
            out[era][v] = row
            print(f"   {v:4}: mean {row['mean_net']:+8,.0f} median {row['median_net']:+8,.0f} P(net>0) {row['p_net_positive']:.0%} "
                  f"p10 {row['net_p10']:+8,.0f} paying {row['streams_paying']:.2f}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--run"); ap.add_argument("--book", action="store_true")
    a = ap.parse_args(argv)
    if a.run:
        run(a.run)
    if a.book:
        (ROOT / "reports" / "a30_book.json").write_text(json.dumps(book(), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
