import bittensor as bt, numpy as np, sys
uid = int(sys.argv[1]); st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); blk = st.get_current_block()
imm = st.query_subtensor("ImmunityPeriod", params=[79]).value; E = np.array(m.emission, dtype=float)
rb = np.array([int(st.query_subtensor("BlockAtRegistration", params=[79, u]).value) for u in range(256)])
non = sorted([u for u in range(1, 256) if blk - rb[u] >= imm], key=lambda u: E[u]); line = E[non[0]]
print(f"UID {uid} age {(blk - rb[uid]) * 12 / 3600:.1f} h | emission ÷ prune line {E[uid] / line:.2f} | lowest unprotected 5 (÷ line): {[round(E[u] / line, 2) for u in non[:5]]} | field median {np.median(E[E > 0]) / line:.2f} | fleet 216 {E[216] / line:.2f}")
