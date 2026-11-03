"""SN101 weights over time (archive node): Tag101 validators set weights = softmax(β·24 h mean score), β 10, so
ln(w_uid / w_median) / 10 = (our 24 h mean − the median miner's). Hourly from START hours ago, for UID OURS, at the largest validator."""
import os, numpy as np, bittensor as bt
net, ours, hours = 101, int(os.environ.get("OURS", "210")), int(os.environ.get("HOURS", "8"))
st = bt.Subtensor(network="archive")
head = st.get_current_block()
m = st.metagraph(net, lite=True); S = np.array(m.S); vp = np.array(m.validator_permit)
val = int(max([v for v in range(len(S)) if vp[v]], key=lambda v: S[v]))
print("validator", val)
for h in range(hours, -1, -1):
    blk = head - h * 300
    w = st.query_subtensor("Weights", block=blk, params=[net, val])
    pairs = w.value if hasattr(w, "value") else w
    arr = np.zeros(256)
    for u, x in pairs: arr[int(u)] = float(x)
    pos = arr[arr > 0]
    med = np.median(pos) if len(pos) else 0
    g = np.log(arr[ours] / med) / 10 if arr[ours] > 0 and med > 0 else float("nan")
    print(f"block {blk} ({h} h ago): uid {ours} weight {arr[ours]:.0f} | median {med:.0f} | 24 h mean gap to median {g:+.4f} | top gap {np.log(pos.max() / med) / 10:+.4f}")
