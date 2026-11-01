"""Out-of-sample check of the near-touch flow pull: per tape, pick THR on the first half of our fills by time, score it on the second half."""
import sys
sys.path.insert(0, "/opt/mvtrx")
import numpy as np
from pull_scan import load
for p in sys.argv[2:]:
    rows = load(p, int(sys.argv[1]))           # fills are in tape (time) order
    h = len(rows) // 2; a, b = rows[:h], rows[h:]
    f = lambda rs: np.array([r[3]["near"] for r in rs]); m = lambda rs: np.array([r[1] for r in rs])
    fa, ma, fb, mb = f(a), m(a), f(b), m(b)
    best = max((0.2, 0.3, 0.4, 0.5, 0.6), key=lambda t: -ma[fa > t].sum())
    for t in sorted({best, 0.3}):
        k = fb <= t
        print(f"{p.split('/')[-1]}: thr {t} ({'picked on 1st half' if t == best else 'deployed'}) → 2nd half: all {mb.mean():+.2f}, kept {mb[k].mean():+.2f} "
              f"({k.mean():.0%} of fills), blocked {mb[~k].mean():+.2f}")
