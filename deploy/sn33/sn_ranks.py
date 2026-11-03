"""Per-validator rank of UID 39 on SN33 (weights are rank-based: transposed cubic over rank, ValidatorLib.get_raw_weights)."""
import numpy as np, bittensor as bt
st = bt.Subtensor(network="finney")
m = st.metagraph(int(__import__("os").environ.get("NET","33")), lite=False)
W = np.array(m.W); S = np.array(m.S); vp = np.array(m.validator_permit)
inc = np.array(m.I); import os; ours, line = int(os.environ.get("OURS","39")), int(os.environ.get("LINE","149"))
vals = [v for v in range(len(S)) if vp[v] and W[v].sum() > 0]
print("validators with weights:", len(vals))
for v in sorted(vals, key=lambda v: -S[v]):
    w = W[v]; pos = w[w > 0]; n = len(pos)
    rank = lambda u: int((w > w[u]).sum())   # 0 = best
    big = w > np.quantile(pos, 0.02)         # ignore baseline-weight (never scored) uids
    print(f"val {v:3d} stake {S[v]:9.0f} | scored {big.sum():3d} | ours rank {rank(ours):3d} from top, {int((w[big] < w[ours]).sum()):3d} below us | uid149 (prune line) {int((w[big] < w[line]).sum()):3d} below")
blk = st.get_current_block(); reg = np.array([int(x) for x in m.block_at_registration])
w = W[max(vals, key=lambda v: S[v])]; below = [u for u in range(len(w)) if 0 < w[u] < w[ours]]; between = [u for u in range(len(w)) if w[ours] < w[u] <= w[line]]
age = lambda u: (blk - reg[u]) * 12 / 3600
print("below us (val 209):", len(below), "| registered < 24 h:", sum(age(u) < 24 for u in below), "| ages h:", sorted(round(age(u), 1) for u in below))
print("between us and the line:", len(between), "| registered < 24 h:", sum(age(u) < 24 for u in between), "| ages h:", sorted(round(age(u)) for u in between))
from collections import Counter
ck = list(m.coldkeys); young = [u for u in range(len(w)) if age(u) < 24]
print("coldkeys of the <24 h uids:", Counter(ck[u][:8] for u in young).most_common(5), "| ours", ck[ours][:8])
print("coldkeys of the 13 between:", Counter(ck[u][:8] for u in between).most_common(4))
old = [u for u in range(len(w)) if age(u) >= 24 and w[u] > 0 and not vp[u]]
print("established (>=24h) miners:", len(old), "| top coldkeys:", Counter(ck[u][:8] for u in old).most_common(5))
