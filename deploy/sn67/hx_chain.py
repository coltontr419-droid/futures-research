import json, urllib.request, bittensor as bt
from collections import defaultdict
N = 67
st = bt.Subtensor("finney"); mg = st.metagraph(N); n = len(mg.uids)
sn = st.subnet(N); price = float(sn.price.tao) if hasattr(sn.price, "tao") else float(sn.price)
tao = json.load(urllib.request.urlopen("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", timeout=20))["bittensor"]["usd"]
usd = price * tao * 7200 / ((st.tempo(N) or 360) + 1) * 30
em = mg.emission.tolist(); vp = mg.validator_permit.tolist()
miners = [u for u in range(n) if not vp[u]]; paid = [u for u in miners if em[u] > 0]
print("SN%d: UIDs %d, miners %d, paid %d | miner pool $%.0f/month | burn %s | TAO $%.0f" % (N, n, len(miners), len(paid), sum(em[u] for u in paid) * usd, st.recycle(N), tao))
v = sorted(em[u] * usd for u in paid)
if v: print("per paid UID $/month: p10 %.0f median %.0f p90 %.0f max %.0f" % (v[len(v) // 10], v[len(v) // 2], v[9 * len(v) // 10], v[-1]))
ck = defaultdict(list)
for u in paid: ck[mg.coldkeys[u]].append(em[u] * usd)
print("paid coldkeys:", len(ck))
for c, x in sorted(ck.items(), key=lambda kv: -sum(kv[1]))[:8]: print("  %s… UIDs %3d  $/month %8.0f  per UID %5.0f" % (c[:8], len(x), sum(x), sum(x) / len(x)))
ax = [mg.axons[u] for u in miners]; print("miners serving an axon:", sum(1 for a in ax if a.ip not in ("0.0.0.0", "") and a.port))
