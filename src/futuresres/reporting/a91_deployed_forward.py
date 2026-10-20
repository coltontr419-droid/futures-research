"""A91 (decisions.md 768): forward record of the DEPLOYED dollar rules on data after the research caches end (from 2026-09-01), using
A49's Yahoo-patched targets — ~3x the demo's information per rule. No trial.

    python -m futuresres.reporting.a91_deployed_forward [--no-refresh]
"""

from __future__ import annotations

import datetime as dt
import importlib
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.a49_watchlist as a49

ROOT = Path(__file__).resolve().parents[3]
#: id -> (module, predictor, target, form, dir)
DEPLOYED = {"D171": ("d119_alldays", "6B=F", "DAX", "all", "fade"), "D174": ("d119_alldays", "DX-Y.NYB", "DAX", "strong", "follow"),
            "D175": ("d119_alldays", "6A=F", "DAX", "strong", "fade"), "D227": ("d120_week", "6E=F", "NKD", "all", "follow")}


def main(argv) -> int:
    if "--no-refresh" not in argv:
        a49.refresh()
    a49.patch_targets(); hi = dt.date.today() - dt.timedelta(days=1); out = {}
    for hid, (mod, p, tg, form, dr) in DEPLOYED.items():
        m = importlib.import_module(f"futuresres.reporting.{mod}")
        carried = json.loads((ROOT / "reports" / f"{mod.split('_')[0]}_discovery.json").read_text())["carried"]
        c = next(x for x in carried if x["predictor"] == p and x["target"] == tg and x["form"] == form and x["dir"] == dr)
        cost = m.TARGETS[tg] if hasattr(m, "TARGETS") and tg in m.TARGETS else 0.5
        D, S, Y = m.rows(p, tg, form, a49.FWD_START, hi, med=c["median_abs"])[:3]
        sg = 1.0 if dr == "follow" else -1.0; net = sg * np.asarray(S) * np.asarray(Y) - cost if len(Y) else np.array([])
        n = len(net); mu = float(net.mean()) if n else float("nan"); t = float(mu / (net.std(ddof=1) / math.sqrt(n))) if n > 2 and net.std() > 0 else float("nan")
        out[hid] = {"rule": f"{tg} {dr}s {p} ({form})", "discovery_net": c["net_bps"], "n": n, "net_bps": mu, "t": t, "sum_bps": float(net.sum()) if n else 0.0}
        print(f"{hid} {out[hid]['rule']:36} research {c['net_bps']:+6.2f} bps | forward from {a49.FWD_START}: n {n:3} net {mu:+7.2f} bps t {t:+5.2f} sum {out[hid]['sum_bps']:+8.1f}", flush=True)
    (ROOT / "reports" / "a91_deployed_forward.json").write_text(json.dumps({"from": str(a49.FWD_START), "through": str(hi), "rules": out}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
