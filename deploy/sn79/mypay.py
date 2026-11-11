"""§1379: x3's current pay in $/month (earnings_all.py formula: emission × 7200/(tempo+1) × alpha price × TAO price × 30), vs UID 216, the field median
and the prune line.   /opt/mvtrx/venv/bin/python mypay.py [uid=64]"""
import json, sys, urllib.request
import bittensor as bt, numpy as np
u = int(sys.argv[1]) if len(sys.argv) > 1 else 64
try:
    tao = json.load(urllib.request.urlopen("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", timeout=20))["bittensor"]["usd"]
except Exception:
    tao = float("nan")
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); blk = st.get_current_block()
tempo = st.query_subtensor("Tempo", params=[79]).value; imm = st.query_subtensor("ImmunityPeriod", params=[79]).value
alpha = float(st.subnet(79).price)
E = np.array(m.emission, dtype=float); usd = E * (7200 / (tempo + 1)) * alpha * tao * 30
rb = np.array([int(st.query_subtensor("BlockAtRegistration", params=[79, i]).value) for i in range(256)])
non = sorted([i for i in range(1, 256) if blk - rb[i] >= imm], key=lambda i: E[i])
paid = np.sort(usd[usd > 0])
nz = [i for i in non if usd[i] > 1.0]   # §1384: a zero-pay unprotected UID (idle / just registered past immunity) sits at the very bottom; show the lowest PAID one too
print(f"PAY UID {u}: ${usd[u]:.0f}/mo (${usd[u] / 30:.2f}/day) | UID 216 ${usd[216]:.0f} | field median ${paid[len(paid) // 2]:.0f} | prune line ${usd[non[0]]:.0f} (lowest unprotected paid > $1 ${usd[nz[0]] if nz else 0:.0f}; x3 ÷ it {usd[u] / usd[nz[0]] if nz else 0:.2f}) | TAO ${tao:.2f}, alpha {alpha:.5f} TAO")
