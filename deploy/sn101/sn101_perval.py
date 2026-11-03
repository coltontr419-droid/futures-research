"""Per SN101 validator: UID OURS's 24 h mean gap to the median, now vs H hours ago (archive). A validator that never reaches us shows our
mean falling toward zero as the inherited entries roll off; one that does shows a steady gap."""
import os, numpy as np, bittensor as bt
net, ours, H = 101, int(os.environ.get("OURS", "210")), int(os.environ.get("H", "6"))
st = bt.Subtensor(network="archive"); head = st.get_current_block()
m = st.metagraph(net, lite=True); S = np.array(m.S); vp = np.array(m.validator_permit)
vals = [v for v in range(len(S)) if vp[v]]
def gap(val, blk):
    w = st.query_subtensor("Weights", block=blk, params=[net, val]); arr = np.zeros(256)
    for u, x in (w.value if hasattr(w, "value") else w): arr[int(u)] = float(x)
    pos = arr[arr > 0]
    return (np.log(arr[ours] / np.median(pos)) / 10 if arr[ours] > 0 and len(pos) else None), len(pos)
for v in sorted(vals, key=lambda v: -S[v]):
    row = [gap(v, head - h * 300) for h in (H, H // 2, 0)]
    if all(r[1] == 0 for r in row): continue
    f = lambda r: "  none " if r[0] is None else f"{r[0]:+.4f}"
    print(f"val {v:3d} stake {S[v]:9.0f} | gap {H} h ago {f(row[0])} | {H // 2} h ago {f(row[1])} | now {f(row[2])} | miners weighted {row[2][1]}")
