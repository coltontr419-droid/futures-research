import numpy as np, bittensor as bt
st = bt.Subtensor(network="archive"); head = st.get_current_block()
for k in (14, 12, 10, 8, 6, 4, 2, 0):
    b = head - k * 7200
    try:
        m = st.metagraph(92, block=b, lite=True); d = st.subnet(92, block=b); tempo = int(d.tempo)
        E = np.array(m.E, dtype=float); vp = np.array(m.validator_permit)
        a = np.sort(np.array([E[u] * (7200 / (tempo + 1)) for u in range(len(vp)) if not vp[u]]))[::-1][3:]   # alpha/day, top 3 excluded
        s = a[a >= 8]
        print(f"day -{k:2d}: strong UIDs (>= 8 alpha/day) {len(s):3d} | their total {s.sum():7.0f} alpha/day | median {np.median(s) if len(s) else 0:5.1f} | "
              f"all other paid UIDs {int(((a > 0.5) & (a < 8)).sum()):3d} share {a[a < 8].sum():6.0f} | price {float(d.price):.5f}", flush=True)
    except Exception as e:
        print(f"day -{k}: error {type(e).__name__} {str(e)[:80]}", flush=True)
