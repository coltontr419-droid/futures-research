"""A55 - Treasury futures (ZB, ZN) as the fifth account instead of MCL (decisions.md 610). No trial."""

from __future__ import annotations

import datetime as dt
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a47_book as a47

ROOT = Path(__file__).resolve().parents[3]
NEW = {"ZB": ("ZB=F", "ZB", 1_000.0, 4.50, 4, (18, True, 16)), "ZN": ("ZN=F", "ZN", 1_000.0, 4.50, 4, (18, True, 16))}


def main() -> int:
    warnings.filterwarnings("ignore"); a22.CAND.update(NEW); s = a23.specs()["50K Daily"]; out = {}
    for m in NEW:
        a22.fetch(NEW[m][0], "1d")
    P = {era: a47.per_start(era) for era in ("pre", "post")}
    for m in NEW:
        res = {}
        for era in ("pre", "post"):
            p, d = a22.daily_paths(m, era); sd1 = float(p[:, -1].std())
            n = int(min(4, max(1, round(2900 / sd1)))); r = a23.replay(s, (p, p, p), n, 4.5)
            dd = [x.astype("datetime64[D]").astype(object) for x in d]
            res[era] = {"contracts": n, "one_contract_sd": sd1, "p_payout": float((r["first"] > 0).mean()), "mean": float(r["net"].mean()),
                        "per_start": {dd[i]: float(x) for i, x in zip(r["start"], r["net"])}}
            print(f"{m} {era}: {n} contracts (1-contract daily SD ${sd1:,.0f}); P(payout) {res[era]['p_payout']:.0%} mean {res[era]['mean']:+,.0f}", flush=True)
        for per, era, lo, hi in (("2010-20", "pre", dt.date(2010, 1, 1), dt.date(2020, 12, 31)), ("2021-26", "post", dt.date(2021, 1, 1), dt.date(2026, 12, 31)),
                                 ("2025 starts", "post", dt.date(2025, 1, 1), dt.date(2026, 12, 31))):
            B = P[era]; X = res[era]["per_start"]
            ds = sorted(d for d in set.intersection(*(set(v) for v in B.values())) & set(X) if lo <= d <= hi)
            cur = np.array([sum(B[k][d] for k in ("MNQ", "MGC", "MCL", "NKD", "FDXM")) for d in ds])
            new = np.array([sum(B[k][d] for k in ("MNQ", "MGC", "NKD", "FDXM")) + X[d] for d in ds])
            corr = float(np.corrcoef([B["MCL"][d] for d in ds], [X[d] for d in ds])[0, 1])
            row = {"starts": len(ds), "book_now": float(cur.mean()), "book_new": float(new.mean()), "p_now": float((cur > 0).mean()), "p_new": float((new > 0).mean()),
                   "p10_now": float(np.percentile(cur, 10)), "p10_new": float(np.percentile(new, 10)), f"{m}_alone": float(np.mean([X[d] for d in ds])),
                   "MCL_alone": float(np.mean([B["MCL"][d] for d in ds]))}
            out[f"{m} | {per}"] = row
            print(f"  book {per} ({len(ds)}): now {row['book_now']:+,.0f} ({row['p_now']:.0%}, p10 {row['p10_now']:+,.0f}) -> with {m} for MCL {row['book_new']:+,.0f} "
                  f"({row['p_new']:.0%}, p10 {row['p10_new']:+,.0f}); MCL {row['MCL_alone']:+,.0f} vs {m} {row[f'{m}_alone']:+,.0f}", flush=True)
    (ROOT / "reports" / "a55_rates.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
