"""Tag101 bench read (§1211 add. 17): per weight update at the largest validator (archive), UID 210's change in 24 h-mean gap MINUS the
field's median change (removes aggregation shifts, which moved the whole field −0.017 at one update), summed per mode slot from
bench_log.txt. Own-round level difference vs the rounds rolling off = 24 × (summed relative change) / slot hours; compare modes."""
import numpy as np, bittensor as bt
st = bt.Subtensor(network="archive"); head = st.get_current_block()
log = [l.split() for l in open("/opt/tag101/bench_log.txt")]
slots = [(l[1], int(l[3])) for l in log]
def gaps(blk):
    w = st.query_subtensor("Weights", block=blk, params=[101, 0]); arr = np.zeros(256)
    for u, x in (w.value if hasattr(w, "value") else w): arr[int(u)] = float(x)
    med = np.median(arr[arr > 0]); return np.where(arr > 0, np.log(np.maximum(arr, 1e-9) / med) / 10, np.nan)
start = slots[0][1] - 1200                                     # ≈ 4 h of verbatim before the bench as the reference
blocks = list(range(start, head, 25)); prev = None; ups = []
for b in blocks:
    g = gaps(b)
    if prev is not None and np.nanmax(np.abs(g - prev)) > 1e-7:
        d = g - prev; ups.append((b, d[210] - np.nanmedian(d), d[210]))
    prev = g
bounds = [("verbatim (before)", start)] + slots + [("end", head)]
print(f"{'mode':18} {'hours':>5} {'updates':>7} {'rel. change':>11} {'raw change':>10} {'per-round vs rolled-off':>24}")
for (m, b0), (_, b1) in zip(bounds, bounds[1:]):
    u = [x for x in ups if b0 <= x[0] < b1]; h = (b1 - b0) * 12 / 3600
    rel = sum(x[1] for x in u); raw = sum(x[2] for x in u)
    print(f"{m:18} {h:5.1f} {len(u):7d} {rel:+11.4f} {raw:+10.4f} {24 * rel / h if h > 0 else 0:+24.3f}")
