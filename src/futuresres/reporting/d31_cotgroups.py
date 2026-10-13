"""D-series family 31 - small-trader (non-reportable) and commercial positioning (decisions.md 230). Same design as d30_cot.

    python -m futuresres.reporting.d31_cotgroups --scan
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np

import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d12_extreme as d12
import futuresres.reporting.d30_cot as d30

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d31_discovery.json"
GROUPS = {"commercial": (11, 12), "small": (15, 16)}


def positions(group: str) -> dict:
    li, si = GROUPS[group]; out = {m: {} for m in d30.CODES}; inv = {v: k for k, v in d30.CODES.items()}
    for f in sorted((ROOT / "data" / "cot").glob("deacot*.zip")):
        z = zipfile.ZipFile(f); rows = csv.reader(io.StringIO(z.read(z.namelist()[0]).decode("latin-1"))); next(rows)
        for r in rows:
            m = inv.get(r[3].strip())
            if m:
                oi = float(r[7]); out[m][dt.date.fromisoformat(r[2].strip())] = (float(r[li]) - float(r[si])) / oi if oi > 0 else np.nan
    return out


def scan() -> dict:
    S = d10.series(); res = []
    for g in GROUPS:
        P = positions(g)
        for m in d30.CODES:
            sig = d30.weekly_signals(P[m])
            for kind in ("flow", "crowding"):
                fol = d30.trades(S, sig, m, kind, 1, *d30.DISC)
                if len(fol) < 50:
                    continue
                gross = np.mean([v for _, _, v in fol]) + d12.COST[m]; direction = 1 if gross > 0 else -1
                tr = fol if direction == 1 else d30.trades(S, sig, m, kind, -1, *d30.DISC)
                x = np.array([v for _, _, v in tr]); t = d30.clustered_t(tr)
                res.append({"group": g, "market": m, "kind": kind, "rule": "follow" if direction == 1 else "fade", "sessions": int(len(x)),
                            "net_bps": float(x.mean()), "t_week": t, "carried": bool(t > 1.96 and x.mean() > 0)})
    res.sort(key=lambda q: -q["t_week"])
    carried = [q for q in res if q["carried"]]
    out = {"window": [str(d30.DISC[0]), str(d30.DISC[1])], "tests": len(res), "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for q in res[:10]:
        print(f"  {q['group']:10} {q['market']:3} {q['kind']:8} {q['rule']:6} sessions {q['sessions']:4} net {q['net_bps']:+6.2f} bps t {q['t_week']:+5.2f}"
              f"{'  CARRIED' if q['carried'] else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
