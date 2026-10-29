# A140: every Fast Track size under the 3-payout transition cap (A135 compared only 100K and 50K). Bracket as A124: take 0.2 x drawdown, stop = drawdown.
# Run: PYTHONPATH=src python scripts/a140_cap_sizes.py
import sys; sys.argv = ["x"]
import importlib.util, io, contextlib
spec = importlib.util.spec_from_file_location("a135", "scripts/a135_three_payout_cap.py"); src = open("scripts/a135_three_payout_cap.py").read().split("cases = {")[0]
ns = {}; exec(src, ns)
import futuresres.reporting.a08_gold as a8
from futuresres.reporting.a124_fast_track_sizes import SIZES
for nm, (p, wdw) in {"MNQ day": ("MNQ", "rth_0930_1600"), "MNQ full": ("MNQ", "full_1800_1655"), "MGC full": ("MGC", "full_1800_1655")}.items():
    for e in ("pre", "post"):
        h, l, c = a8.era_paths(e, p, wdw)[:3]
        out = []
        for sz in ("25K", "50K", "100K", "150K"):
            dd = SIZES[sz]["dd"]; v, pp = ns["sim"](h, l, c, 3, 0, 0.2 * dd, dd, sz); out.append(f"{sz} {v:+7,.0f} ({pp:.1f})")
        print(f"{nm:9} {e:4} | " + " | ".join(out), flush=True)
