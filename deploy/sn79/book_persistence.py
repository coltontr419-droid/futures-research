import json, subprocess, sys
import numpy as np
from collections import defaultdict
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import accumulate_book_capture
def per_book(path, me):
    tr = defaultdict(list)
    for l in open(path):
        r = json.loads(l)
        if "p" in r: tr[r["book"]].append({"p": r["p"], "q": r["q"], "s": r["s"], "Ma": r.get("Ma", -1), "Ta": r.get("Ta", -1), "Mf": r.get("Mf") or 0.0, "t": r["ts"]})
    cb, cs, rb, rs = (defaultdict(dict) for _ in range(4)); tb, ts = {}, {}
    for b, t in tr.items():
        t.sort(key=lambda x: x["t"])
        accumulate_book_capture(cb, cs, b, t, 15, buy_hist={}, sell_hist={}, ts=t[-1]["t"], mid_state=None, real_buy_sums=rb, real_sell_sums=rs,
                                real_buy_hist={}, real_sell_hist={}, horizon_ns=20_000_000_000, now_ns=t[-1]["t"], min_size=0.25, fee_weight=0.005, market_votes=False, taker=(tb, ts, {}, {}))
    return {b: rb.get(me, {}).get(b, 0.0) + rs.get(me, {}).get(b, 0.0) for b in set(rb.get(me, {})) | set(rs.get(me, {}))}
tapes = ["/opt/mvtrx/live_tape_x1_%s.jsonl" % t for t in ("of", "pull1", "fast", "cancelfirst")]
R = [per_book(t, 93) for t in tapes]
for i in range(len(R) - 1):
    common = sorted(set(R[i]) & set(R[i + 1])); a = np.array([R[i][b] for b in common]); c = np.array([R[i + 1][b] for b in common])
    rk = lambda x: np.argsort(np.argsort(x))
    n1 = tapes[i].split("x1_")[1]; n2 = tapes[i + 1].split("x1_")[1]; rho = np.corrcoef(rk(a), rk(c))[0, 1]
    print(n1, "->", n2, "books", len(common), "rank correlation of per-book realized R %+.2f" % rho)
