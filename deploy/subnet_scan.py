"""Bittensor subnet scan (decisions.md §1212): per subnet, miner pay distribution ($/month from incentive × miner emission), the
lowest non-immune miner, registration burn, miner count, and wallet concentration (top coldkey's share of miners)."""
import json, sys, time, urllib.request
from collections import Counter
import numpy as np
import bittensor as bt
st = bt.Subtensor(network="finney")
tao = json.load(urllib.request.urlopen("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", timeout=20))["bittensor"]["usd"]
nets = st.get_all_subnets_netuid() if hasattr(st, "get_all_subnets_netuid") else st.get_subnets()
head = st.get_current_block(); out = []
for n in nets:
    if n == 0: continue
    try:
        m = st.metagraph(n, lite=True)
        dyn = st.subnet(n)
        price = float(dyn.price) if dyn else 0.0                     # TAO per alpha
        E = np.array(m.E, dtype=float) if hasattr(m, "E") else np.array(m.emission, dtype=float)
        vp = np.array(m.validator_permit); I = np.array(m.I, dtype=float)
        tempo = int(getattr(dyn, "tempo", 360) or 360)
        miners = [u for u in range(len(vp)) if not vp[u]]
        if len(miners) < 8: continue
        # m.E is alpha per tempo per uid
        pm = lambda u: float(E[u]) * (7200 / (tempo + 1)) * price * tao * 30
        pay = np.array([pm(u) for u in miners])
        reg = np.array([int(x) for x in m.block_at_registration]) if hasattr(m, "block_at_registration") else None
        imm = 7200
        old = [pm(u) for u in miners if reg is not None and head - reg[u] > imm]
        ck = Counter(m.coldkeys[u] for u in miners)
        burn = float(st.recycle(n)) if hasattr(st, "recycle") else float("nan")
        out.append(dict(net=n, name=str(getattr(dyn, "subnet_name", "") or ""), miners=len(miners), med=float(np.median(pay)), p75=float(np.percentile(pay, 75)),
                        p90=float(np.percentile(pay, 90)), line=float(min(old)) if old else float("nan"), burn=burn,
                        topck=ck.most_common(1)[0][1] / len(miners), nck=len(ck), paid=float((pay > 50).mean())))
        print(n, out[-1]["name"][:20], round(out[-1]["med"]), flush=True)
    except Exception as e:
        print(n, "error", type(e).__name__, str(e)[:80], flush=True)
json.dump(out, open("/opt/mvtrx/subnet_scan.json", "w"))
