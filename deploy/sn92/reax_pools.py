import json, urllib.request, numpy as np, bittensor as bt
from collections import defaultdict
st = bt.Subtensor(network="finney"); m = st.metagraph(92, lite=True); d = st.subnet(92)
tao = json.load(urllib.request.urlopen("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", timeout=20))["bittensor"]["usd"]
E = np.array(m.E, dtype=float); vp = np.array(m.validator_permit); price = float(d.price); tempo = int(d.tempo)
pm = lambda u: E[u] * (7200 / (tempo + 1)) * price * tao * 30
pools = defaultdict(list); unknown = 0
for u in range(len(vp)):
    if vp[u]: continue
    c = None
    try:
        c = st.get_commitment(92, u)
    except Exception:
        pass
    tag = "none"
    if c:
        s = str(c)
        for k in ("s1-cpu", "s1-lite", "s1-fast", "s1-pro", "mammoth", "plumb", "gutsy", "rune"):
            if k in s.lower(): tag = k; break
        else: tag = s[:30]
    pools[tag].append(pm(u))
print(f"SN92 by committed model (TAO ${tao:.0f}, REAX price {price:.5f} TAO, pool TAO {float(d.tao_in):,.0f}):")
for k, v in sorted(pools.items(), key=lambda kv: -sum(kv[1])):
    v = np.array(v); print(f"  {k:32} UIDs {len(v):3d} | total ${v.sum():9,.0f} | median ${np.median(v):7,.0f} | p75 ${np.percentile(v,75):7,.0f} | paid>$50: {(v>50).sum()}")
