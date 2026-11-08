import bittensor as bt, numpy as np
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); blk = st.get_current_block()
imm = st.query_subtensor("ImmunityPeriod", params=[79]).value; E = np.array(m.emission, dtype=float)
rb = np.array([int(st.query_subtensor("BlockAtRegistration", params=[79, u]).value) for u in range(256)])
age = (blk - rb) * 12 / 86400
non = sorted([u for u in range(1, 256) if blk - rb[u] >= imm], key=lambda u: E[u]); line = E[non[0]]
fl = sorted([u for u in range(256) if m.coldkeys[u].startswith("5F1F2JMu")], key=lambda u: age[u])
print(f"prune line (lowest unprotected) = 1.00; x2 {E[212]/line:.2f}, x4 {E[58]/line:.2f}; field median {np.median(E[E>0])/line:.2f}")
for lo, hi in ((0, 1), (1, 2), (2, 6), (6, 12), (12, 99)):
    g = [u for u in fl if lo <= age[u] < hi]
    if g: print(f"fleet age {lo}-{hi} d: {len(g):2d} UIDs, emission / line: min {min(E[u] for u in g)/line:.2f} median {np.median([E[u] for u in g])/line:.2f} max {max(E[u] for u in g)/line:.2f}")
print("youngest fleet UIDs (age d, emission/line):", [(u, round(age[u], 2), round(E[u]/line, 2)) for u in fl[:8]])
oth = [u for u in range(256) if age[u] < 2 and not m.coldkeys[u].startswith("5F1F2JMu")]
print(f"non-fleet UIDs < 2 d old: {len(oth)}, emission/line median {np.median([E[u] for u in oth])/line:.2f}")
