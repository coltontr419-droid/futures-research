import json, urllib.request, urllib.parse, bittensor as bt, numpy as np
P = "https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query"
def q(expr):
    u = P + "?" + urllib.parse.urlencode({"query": expr})
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "curl/8.5.0"}), timeout=30))["data"]["result"]
W = 'wallet=~"5EWwdZB7.*"'
g = lambda n: {int(x["metric"]["agent_id"]): float(x["value"][1]) for x in q('max by (agent_id) (miner_gauges{miner_gauge_name="%s",%s})' % (n, W))}
mk, sk, na = g("debeta_making"), g("debeta_skill"), g("debeta_skill_net_alpha")
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); b = st.get_current_block()
tao = json.load(urllib.request.urlopen(urllib.request.Request("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", headers={"User-Agent": "curl/8.5.0"}), timeout=20))["bittensor"]["usd"]
tempo = st.query_subtensor("Tempo", params=[79]).value; alpha = float(st.subnet(79).price)
E = np.array(m.emission, dtype=float) * (7200 / (tempo + 1)) * alpha * tao * 30
age = {u: (b - int(st.query_subtensor("BlockAtRegistration", params=[79, u]).value)) * 12 / 86400 for u in range(256)}
rows = sorted(range(256), key=lambda u: -E[u])
print("top 25 by pay: uid | $/mo | age d | making | skill | net alpha")
for u in rows[:25]: print(f"  {u:3d} | ${E[u]:5.0f} | {age[u]:5.1f} | {mk.get(u, 0):7.1f} | {sk.get(u, 0):6.2f} | {na.get(u, 0):8.0f}")
for lo, hi in ((0, 2), (2, 7), (7, 14), (14, 999)):
    us = [u for u in range(256) if lo <= age[u] < hi]
    mm = [u for u in us if mk.get(u, 0) > 0]
    print(f"age {lo}-{hi} d: {len(us)} uids | making>0 {len(mm)} | median making (makers) {np.median([mk[u] for u in mm]) if mm else 0:.0f} | median pay makers ${np.median([E[u] for u in mm]) if mm else 0:.0f} | median pay skill-only ${np.median([E[u] for u in us if mk.get(u,0) <= 0 and sk.get(u,0) > 0] or [0]):.0f}")
