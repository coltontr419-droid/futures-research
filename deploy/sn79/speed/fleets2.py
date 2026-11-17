import json, urllib.request, urllib.parse, bittensor as bt, numpy as np, collections
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
C = collections.defaultdict(list)
for u in range(1, 256): C[ck[u]].append(u)
print("coldkey  | UIDs | total $/mo | median | min–max | ages d (min/med/max) | making>0 | skill>0 | median net alpha | median making | median coverage")
fl = {}
for c, us in sorted(C.items(), key=lambda x: -sum(E[u] for u in x[1])):
    if len(us) < 8: continue
    fl[c[:8]] = us
    print(f"{c[:8]} | {len(us):4d} | ${sum(E[u] for u in us):7,.0f} | ${np.median([E[u] for u in us]):4.0f} | ${min(E[u] for u in us):.0f}–{max(E[u] for u in us):.0f} | "
          f"{min(age[u] for u in us):.1f}/{np.median([age[u] for u in us]):.1f}/{max(age[u] for u in us):.1f} | {sum(1 for u in us if mk.get(u,0) > 0):3d} | {sum(1 for u in us if sk.get(u,0) > 0):3d} | "
          f"{np.median([na.get(u,0) for u in us]):6.0f} | {np.median([mk.get(u,0) for u in us]):5.1f} | {np.median([cov.get(u,0) for u in us]):4.0f}")
json.dump(fl, open("/opt/mvtrx/speed/fleets.json", "w"))
tot = sum(E[1:]); print(f"all miners $/mo ≈ {tot:,.0f}; fleets ≥ 8 UIDs hold {sum(sum(E[u] for u in us) for us in fl.values()) / tot:.0%}")
