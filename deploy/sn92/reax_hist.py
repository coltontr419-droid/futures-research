"""REAX pay history: per day for 14 days, from the archive node — alpha per day per miner UID (top band, count over thresholds) and the
REAX price, so pay trends can be separated from price trends."""
import numpy as np, bittensor as bt
st = bt.Subtensor(network="archive"); head = st.get_current_block()
for k in range(14, -1, -1):
    b = head - k * 7200
    try:
        m = st.metagraph(92, block=b, lite=True); d = st.subnet(92, block=b)
        E = np.array(m.E, dtype=float); vp = np.array(m.validator_permit); tempo = int(d.tempo); price = float(d.price)
        a = np.array([E[u] * (7200 / (tempo + 1)) for u in range(len(vp)) if not vp[u]])   # alpha per day per miner UID
        s = np.sort(a)[::-1]
        band = s[3:60]                                       # excludes the top 3 (spec-competition winners)
        print(f"day -{k:2d} block {b}: price {price:.5f} TAO | alpha/day: UIDs > 100: {(a > 100).sum():3d}, > 400: {(a > 400).sum():3d} | median of ranks 4-60 {np.median(band):7.1f} | total miner {a.sum():8.0f}", flush=True)
    except Exception as e:
        print(f"day -{k}: error {type(e).__name__} {str(e)[:80]}", flush=True)
