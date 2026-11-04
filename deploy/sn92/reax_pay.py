import json, urllib.request, numpy as np, bittensor as bt
from collections import Counter
st = bt.Subtensor(network="finney"); m = st.metagraph(92, lite=True); d = st.subnet(92)
tao = json.load(urllib.request.urlopen("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", timeout=20))["bittensor"]["usd"]
E = np.array(m.E, dtype=float); vp = np.array(m.validator_permit); price = float(d.price); tempo = int(d.tempo)
pm = lambda u: E[u] * (7200 / (tempo + 1)) * price * tao * 30
owner = d.owner_hotkey if hasattr(d, "owner_hotkey") else None
pay = sorted(((pm(u), u) for u in range(len(vp)) if not vp[u]), reverse=True)
v = np.array([p for p, _ in pay])
print(f"SN92: {len(v)} miner UIDs | total ${v.sum():,.0f}/month | owner hotkey {str(owner)[:8]}")
for lo, hi in ((2000, 1e9), (500, 2000), (150, 500), (50, 150), (1, 50), (0, 1)):
    b = v[(v >= lo) & (v < hi)]; print(f"  ${lo:>5}-{'up' if hi >= 1e9 else int(hi):>5}: {len(b):3d} UIDs, total ${b.sum():9,.0f}")
print("top 6:", [(round(p), u, m.hotkeys[u][:6], m.coldkeys[u][:6]) for p, u in pay[:6]])
ck = Counter(m.coldkeys[u] for p, u in pay if p > 1); print("paying wallets:", len(ck), "| biggest:", [(k[:6], n) for k, n in ck.most_common(4)])
