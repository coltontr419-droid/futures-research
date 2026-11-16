import json, urllib.request, urllib.parse, bittensor as bt, numpy as np, collections
P = "https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query"
def q(expr):
    u = P + "?" + urllib.parse.urlencode({"query": expr})
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "curl/8.5.0"}), timeout=30))["data"]["result"]
W = 'wallet=~"5EWwdZB7.*"'
g = lambda n: {int(x["metric"]["agent_id"]): float(x["value"][1]) for x in q('max by (agent_id) (miner_gauges{miner_gauge_name="%s",%s})' % (n, W))}
G = {n: g(n) for n in ("debeta_skill", "debeta_skill_net_alpha", "debeta_making", "debeta_coverage_books", "debeta_skill_books_kept")}
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); b = st.get_current_block()
tao = json.load(urllib.request.urlopen(urllib.request.Request("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", headers={"User-Agent": "curl/8.5.0"}), timeout=20))["bittensor"]["usd"]
tempo = st.query_subtensor("Tempo", params=[79]).value; alpha = float(st.subnet(79).price)
E = np.array(m.emission, dtype=float) * (7200 / (tempo + 1)) * alpha * tao * 30
ck = list(m.coldkeys)
cnt = collections.Counter(ck)
print("coldkeys with >= 4 UIDs:", [(c[:8], n, round(float(sum(E[u] for u in range(256) if ck[u] == c)))) for c, n in cnt.most_common() if n >= 4])
fl = [u for u in range(256) if ck[u].startswith("5F1F2JMu")]
age = {u: (b - int(st.query_subtensor("BlockAtRegistration", params=[79, u]).value)) * 12 / 86400 for u in fl}
print(f"fleet 5F1F2JMu: {len(fl)} uids, total ${sum(E[u] for u in fl):,.0f}/mo, median ${np.median([E[u] for u in fl]):.0f}")
print("uid | $/mo | age d | skill | net alpha | kept | coverage | making")
for u in sorted(fl, key=lambda u: -E[u]):
    print(f"{u:3d} | {E[u]:4.0f} | {age[u]:5.1f} | {G['debeta_skill'].get(u, 0):5.2f} | {G['debeta_skill_net_alpha'].get(u, 0):7.0f} | {G['debeta_skill_books_kept'].get(u, 0):3.0f} | {G['debeta_coverage_books'].get(u, 0):3.0f} | {G['debeta_making'].get(u, 0):5.1f}")
json.dump(fl, open("/opt/mvtrx/speed/fleet_uids.json", "w"))
