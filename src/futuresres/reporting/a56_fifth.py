"""A56 - the best zero-edge fifth market: every feasible candidate in MCL's slot (decisions.md 612). No trial."""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a47_book as a47

ROOT = Path(__file__).resolve().parents[3]
#: market -> (Yahoo symbol, contract, $ multiplier, round trip, cap, session)
NEW = {"ZB": ("ZB=F", "ZB", 1_000.0, 4.50, 4, None), "ZN": ("ZN=F", "ZN", 1_000.0, 4.50, 4, None),
       "6E": ("6E=F", "6E", 125_000.0, 4.50, 4, None), "6J": ("6J=F", "6J", 12_500_000.0, 4.50, 4, None),
       "6A": ("6A=F", "6A", 100_000.0, 4.50, 4, None), "6B": ("6B=F", "6B", 62_500.0, 4.50, 4, None),
       "SI": ("SI=F", "SI", 5_000.0, 4.50, 4, None), "PL": ("PL=F", "PL", 50.0, 4.50, 4, None),
       "NG": ("NG=F", "MNG", 1_000.0, 3.32, 40, None), "HG": ("HG=F", "MHG", 2_500.0, 3.32, 40, None),
       "ZC": ("ZC=F", "ZC", 50.0, 4.50, 4, None), "ZW": ("ZW=F", "ZW", 50.0, 4.50, 4, None),
       "LE": ("LE=F", "LE", 400.0, 4.50, 4, None), "HE": ("HE=F", "HE", 400.0, 4.50, 4, None)}
PER = (("2010-20", "pre", dt.date(2010, 1, 1), dt.date(2020, 12, 31)), ("2021-26", "post", dt.date(2021, 1, 1), dt.date(2026, 12, 31)),
       ("2025 starts", "post", dt.date(2025, 1, 1), dt.date(2026, 12, 31)))


def main() -> int:
    warnings.filterwarnings("ignore"); s = a23.specs()["50K Daily"]; out = {}
    for m, v in NEW.items():
        a22.CAND[m] = v
        try:
            a22.fetch(v[0], "1d"); time.sleep(0.3)
        except Exception:
            pass
    P = {era: a47.per_start(era) for era in ("pre", "post")}
    for m, v in NEW.items():
        X = {}; info = {}
        for era in ("pre", "post"):
            try:
                p, d = a22.long_paths(m, era)
            except Exception as e:
                print(f"{m} {era}: no paths ({type(e).__name__})"); break
            sd1 = float(p[:, -1].std()); n = int(min(v[4], max(1, round(2900 / sd1))))
            r = a23.replay(s, (p, p, p), n, v[3]); dd = [x.astype("datetime64[D]").astype(object) for x in d]
            X.update({dd[i]: float(x) for i, x in zip(r["start"], r["net"])}); info[era] = (n, sd1)
        row = {"contracts": {k: x[0] for k, x in info.items()}}; ok = True
        for per, era, lo, hi in PER:
            B = P[era]; ds = sorted(d for d in set.intersection(*(set(x) for x in B.values())) & set(X) if lo <= d <= hi)
            if not ds:
                ok = False; continue
            cur = np.array([sum(B[k][d] for k in ("MNQ", "MGC", "MCL", "NKD", "FDXM")) for d in ds])
            new = np.array([sum(B[k][d] for k in ("MNQ", "MGC", "NKD", "FDXM")) + X[d] for d in ds])
            row[per] = {"n": len(ds), "now": float(cur.mean()), "new": float(new.mean()), "p_now": float((cur > 0).mean()), "p_new": float((new > 0).mean()),
                        "p10_now": float(np.percentile(cur, 10)), "p10_new": float(np.percentile(new, 10))}
            ok &= row[per]["new"] > row[per]["now"]
        row["qualifies"] = bool(ok); out[m] = row
        print(f"{m:3} ({row['contracts']}): " + " | ".join(f"{per} {row[per]['now']:+,.0f}→{row[per]['new']:+,.0f} ({row[per]['p_now']:.0%}→{row[per]['p_new']:.0%})"
                                                         for per, *_ in PER if per in row) + ("  QUALIFIES" if ok else ""), flush=True)
    (ROOT / "reports" / "a56_fifth.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
