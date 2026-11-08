import bittensor as bt, numpy as np
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); blk = st.get_current_block()
imm = st.query_subtensor("ImmunityPeriod", params=[79]).value; E = np.array(m.emission, dtype=float)
rb = np.array([int(st.query_subtensor("BlockAtRegistration", params=[79, u]).value) for u in range(256)])
non = sorted([u for u in range(1, 256) if blk - rb[u] >= imm], key=lambda u: E[u])
print("lowest unprotected vs x2:", [round(E[u] / E[212], 2) for u in non[:6]], "| x4/x2", round(E[58] / E[212], 2), "| unprotected", len(non))
recent = sorted(blk - rb[u] for u in range(256) if blk - rb[u] < 7200)
print("registrations in the last 6 h:", sum(1 for d in recent if d < 1800), "| last 24 h:", len(recent))
print("burn (registration cost) TAO:", st.recycle(79))
ck = open("/root/.bittensor/wallets/main/coldkeypub.txt").read()
import json; ck = json.loads(ck)["ss58Address"]
print("coldkey free balance TAO:", st.get_balance(ck))
