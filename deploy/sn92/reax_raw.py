import json, urllib.request, numpy as np, bittensor as bt
from collections import Counter
st = bt.Subtensor(network="finney"); m = st.metagraph(92, lite=True); d = st.subnet(92)
tao = json.load(urllib.request.urlopen("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", timeout=20))["bittensor"]["usd"]
E = np.array(m.E, dtype=float); vp = np.array(m.validator_permit); price = float(d.price); tempo = int(d.tempo)
pm = lambda u: E[u] * (7200 / (tempo + 1)) * price * tao * 30
rows = []
for u in range(len(vp)):
    if vp[u]: continue
    try: c = str(st.get_commitment(92, u) or "")
    except Exception: c = ""
    rows.append((pm(u), u, c))
rows.sort(reverse=True)
print("top 12 by pay:")
for p, u, c in rows[:12]: print(f"  ${p:8,.0f} uid {u:3d} | {c[:110]}")
shape = Counter()
for p, u, c in rows:
    kinds = tuple(sorted({k for k in ("s1-cpu", "s1-lite", "s1-fast", "s1-pro") if k in c})) or (c.split(":")[0][:20],)
    shape[kinds] += 1
print("commitment shapes:", shape.most_common(8))
cpu_only = [p for p, u, c in rows if "s1-cpu" in c and not any(k in c for k in ("s1-lite", "s1-fast", "s1-pro"))]
print(f"cpu-only UIDs {len(cpu_only)}: total ${sum(cpu_only):,.0f}, median ${np.median(cpu_only) if cpu_only else 0:,.0f}, p25 ${np.percentile(cpu_only,25) if cpu_only else 0:,.0f}, p75 ${np.percentile(cpu_only,75) if cpu_only else 0:,.0f}")
