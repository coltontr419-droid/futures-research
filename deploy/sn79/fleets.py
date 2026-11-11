"""§1380: why is x3 below the median pay? Every UID: chain $/month + live gauges (making, skill, combined). Where does the median miner's pay come from?
   /opt/mvtrx/venv/bin/python paysplit.py"""
import json, subprocess, urllib.request
import bittensor as bt, numpy as np
P = "https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query"
def g(name):
    r = subprocess.run(["curl", "-s", "-G", P, "--data-urlencode", f'query=max by (agent_id) (miner_gauges{{miner_gauge_name="{name}"}})'], capture_output=True, text=True).stdout
    return {int(x["metric"]["agent_id"]): float(x["value"][1]) for x in json.loads(r)["data"]["result"] if x["metric"].get("agent_id", "").isdigit()}
mk, sk, cb = g("debeta_making"), g("debeta_skill"), g("combined_score")
tao = json.load(urllib.request.urlopen("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", timeout=20))["bittensor"]["usd"]
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); tempo = st.query_subtensor("Tempo", params=[79]).value; blk = st.get_current_block()
alpha = float(st.subnet(79).price); E = np.array(m.emission, dtype=float); usd = E * (7200 / (tempo + 1)) * alpha * tao * 30
age = np.array([(blk - int(st.query_subtensor("BlockAtRegistration", params=[79, u]).value)) * 12 / 86400 for u in range(256)])
import collections
g = collections.defaultdict(list)
for u in range(1, 256): g[m.coldkeys[u][:8]].append(u)
print("owners with >= 4 UIDs: coldkey | n | making-only n | ages (median, n >= 7 d) | pay median / total | making median")
for ck, us in sorted(g.items(), key=lambda kv: -len(kv[1])):
    if len(us) < 4: continue
    mo = [u for u in us if sk.get(u, 0) == 0 and mk.get(u, 0) > 0]
    a = sorted(age[u] for u in us); p = sorted(usd[u] for u in us); mm = sorted(mk.get(u, 0) for u in mo)
    print(f"  {ck} | {len(us):3d} | {len(mo):3d} | age med {a[len(a)//2]:4.1f} d, ≥7 d: {sum(x >= 7 for x in a):3d} | ${p[len(p)//2]:.0f} / ${sum(p):,.0f} | making med {mm[len(mm)//2] if mm else 0:.0f}")
    print("      UIDs ≥ 7 d making-only:", sorted(u for u in mo if age[u] >= 7))
