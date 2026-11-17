import json, urllib.request, urllib.parse, bittensor as bt, numpy as np
P = "https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query"
def q(expr):
    u = P + "?" + urllib.parse.urlencode({"query": expr})
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "curl/8.5.0"}), timeout=30))["data"]["result"]
W = 'wallet=~"5EWwdZB7.*"'
g = lambda n: {int(x["metric"]["agent_id"]): float(x["value"][1]) for x in q('max by (agent_id) (miner_gauges{miner_gauge_name="%s",%s})' % (n, W))}
mk, sk, na, cov = g("debeta_making"), g("debeta_skill"), g("debeta_skill_net_alpha"), g("debeta_coverage_books")
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); b = st.get_current_block()
tao = json.load(urllib.request.urlopen(urllib.request.Request("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", headers={"User-Agent": "curl/8.5.0"}), timeout=20))["bittensor"]["usd"]
tempo = st.query_subtensor("Tempo", params=[79]).value; alpha = float(st.subnet(79).price)
E = np.array(m.emission, dtype=float) * (7200 / (tempo + 1)) * alpha * tao * 30; ck = list(m.coldkeys)
age = {u: (b - int(st.query_subtensor("BlockAtRegistration", params=[79, u]).value)) * 12 / 86400 for u in range(256)}
mak = sorted([u for u in range(256) if mk.get(u, 0) > 0], key=lambda u: -mk[u])
print(f"makers (making > 0): {len(mak)}; Σ making {sum(mk[u] for u in mak):,.0f}; pay of makers ${sum(E[u] for u in mak):,.0f}/mo")
print("top 20 by making credit: uid | making | $/mo | age d | skill | net alpha | coverage | coldkey")
for u in mak[:20]: print(f"  {u:3d} | {mk[u]:6.1f} | ${E[u]:5.0f} | {age[u]:5.1f} | {sk.get(u,0):5.2f} | {na.get(u,0):7.0f} | {cov.get(u,0):3.0f} | {ck[u][:8]}")
lm = [u for u in mak if age[u] >= 7]
print(f"long-lived makers (≥ 7 d): {len(lm)} →", [(u, round(mk[u]), round(E[u]), round(age[u], 1)) for u in sorted(lm, key=lambda u: -mk[u])[:12]])
pay_per = [E[u] / mk[u] for u in mak if mk[u] > 20 and sk.get(u, 0) <= 0]
print(f"$ per unit making credit (making-only UIDs, credit > 20): median {np.median(pay_per):.2f}, n {len(pay_per)}")
