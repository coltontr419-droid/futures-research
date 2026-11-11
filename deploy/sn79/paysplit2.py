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
paid = sorted(usd[1:][usd[1:] > 0]); med = paid[len(paid) // 2]
print(f"field pay median ${med:.0f}")
for lo, hi, lab in ((0, 3, "0-3 d"), (3, 7, "3-7 d"), (7, 1e9, "≥ 7 d")):
    for cls in ("making only", "skill (any)"):
        v = [u for u in range(1, 256) if lo <= age[u] < hi and ((sk.get(u, 0) == 0 and mk.get(u, 0) > 0) if cls == "making only" else sk.get(u, 0) > 0)]
        p = sorted(usd[u] for u in v); q = lambda f: p[int(f * (len(p) - 1))] if p else 0
        print(f"  age {lab:6s} {cls:12s}: n {len(v):3d} | pay p25 ${q(.25):.0f} median ${q(.5):.0f} p75 ${q(.75):.0f} p90 ${q(.9):.0f}")
ll = sorted([u for u in range(1, 256) if age[u] >= 7 and sk.get(u, 0) == 0 and mk.get(u, 0) > 0], key=lambda u: -usd[u])
print("long-lived (≥ 7 d) making-only by PAY: uid age making pay coldkey")
for u in ll[:12]: print(f"  {u:3d} {age[u]:5.1f} d  making {mk.get(u, 0):5.0f}  ${usd[u]:.0f}  {m.coldkeys[u][:8]}")
r = sorted(ll, key=lambda u: -usd[u]); print(f"x3 64: age {age[64]:.1f} d, ${usd[64]:.0f}; would rank {sum(usd[u] > usd[64] for u in ll) + 1} of {len(ll) + 1} among long-lived making-only")
