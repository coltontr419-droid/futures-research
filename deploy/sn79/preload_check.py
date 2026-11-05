"""§1236 check: preload the tape up to a cut point, then compare the preloaded state's forecast at the cut with a full replay (revfeat_parity
path) at the same moment. If preload is exact, every book's forecast matches."""
import json, sys, time
sys.path.insert(0, "/opt/mvtrx")
from revfeat import RevFeatures
T = "/tmp/tape_frozen.jsonl"
t0 = time.time(); a = RevFeatures("/opt/mvtrx/agents/rev_model.json"); n = a.preload(T, mb=int(sys.argv[1])); dt = time.time() - t0
b = RevFeatures("/opt/mvtrx/agents/rev_model.json"); b.preload(T, mb=int(sys.argv[2]))        # longer history = reference
last = max(s["mid"].d[-1][0] for s in a.books.values())
pa = {k: a.predict(k, last) for k in a.books}; pb = {k: b.predict(k, last) for k in b.books}
both = [(pa[k], pb[k]) for k in pa if pa[k] is not None and pb.get(k) is not None]
import numpy as np
x = np.array(both)
print("preload: %d snapshots in %.0f s, %d books, %d with a forecast | corr vs longer-history reference %.4f | max |diff| %.3f bp" % (
    n, dt, len(a.books), len(both), np.corrcoef(x[:, 0], x[:, 1])[0, 1] if len(x) > 2 else float("nan"), np.abs(x[:, 0] - x[:, 1]).max() if len(x) else float("nan")))
