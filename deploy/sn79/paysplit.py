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
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); tempo = st.query_subtensor("Tempo", params=[79]).value
alpha = float(st.subnet(79).price); E = np.array(m.emission, dtype=float); usd = E * (7200 / (tempo + 1)) * alpha * tao * 30
fl = {u for u in range(256) if m.coldkeys[u].startswith("5F1F2JMu")}
rows = [(u, usd[u], mk.get(u, 0), sk.get(u, 0), cb.get(u, 0)) for u in range(1, 256)]
paid = sorted(r[1] for r in rows if r[1] > 0); med = paid[len(paid) // 2]
cls = lambda r: "skill+making" if r[3] > 0 and r[2] > 0 else ("skill only" if r[3] > 0 else ("making only" if r[2] > 0 else "neither"))
print(f"UIDs {len(rows)} | pay median ${med:.0f} | TAO ${tao:.0f}")
import collections
by = collections.defaultdict(list)
for r in rows: by[cls(r)].append(r)
for k, v in by.items():
    p = sorted(x[1] for x in v); q = lambda a, f: a[int(f * (len(a) - 1))] if a else 0
    print(f"  {k:13s}: n {len(v):3d} | pay p25 ${q(p, .25):.0f} median ${q(p, .5):.0f} p75 ${q(p, .75):.0f} | above field median: {sum(x[1] > med for x in v)}")
mo = sorted([r for r in rows if r[3] == 0 and r[2] > 0], key=lambda r: -r[2])
print("making-only miners by making credit (rank: uid, making, pay):")
for i, r in enumerate(mo[:12]): print(f"  {i + 1:2d}. UID {r[0]:3d}{' F' if r[0] in fl else '  '} making {r[2]:6.0f} pay ${r[1]:.0f}")
x3 = [i for i, r in enumerate(mo) if r[0] == 64]
print(f"x3 rank among {len(mo)} making-only miners: {x3[0] + 1 if x3 else None} | making-only pay median ${sorted(r[1] for r in mo)[len(mo) // 2]:.0f}")
# pay vs making for making-only: slope
a = np.array([[r[2], r[1]] for r in mo if r[1] > 0]); k = (a[:, 0] @ a[:, 1]) / (a[:, 0] @ a[:, 0])
print(f"making-only: pay ≈ ${k:.3f} per making point (x3 at that rate ${k * mk.get(64, 0):.0f}); making needed for the field median ≈ {med / k:.0f}")
