import json, numpy as np, bittensor as bt
c = {int(r["metric"]["agent_id"]): float(r["value"][1]) for r in json.load(open("/tmp/g_combined_score.json"))["data"]["result"]}
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); blk = st.get_current_block()
imm = st.query_subtensor("ImmunityPeriod", params=[79]).value; E = np.array(m.emission, dtype=float)
rb = np.array([int(st.query_subtensor("BlockAtRegistration", params=[79, u]).value) for u in range(256)]); age = (blk - rb) * 12 / 86400
non = [u for u in range(1, 256) if blk - rb[u] >= imm]; line = min(E[u] for u in non)
S = 0.195
lo = [u for u in non if c.get(u, 0) < S]
print(f"unprotected UIDs: {len(non)} | with live combined below x3 steady {S}: {len(lo)} | protected newcomers: {256 - 1 - len(non)}")
set_ = [u for u in non if age[u] >= 3]
x = np.array([c.get(u, 0) for u in set_]); y = np.array([E[u] / line for u in set_])
b = np.polyfit(x, y, 1); print(f"settled (>= 3 d) UIDs n {len(set_)}: pay/line ≈ {b[1]:.2f} + {b[0]:.2f} × live combined → at {S}: {b[1] + b[0] * S:.2f}×")
for lo_, hi_ in ((0, .1), (.1, .2), (.2, .3), (.3, .4), (.4, 1)):
    g = [E[u] / line for u in set_ if lo_ <= c.get(u, 0) < hi_]
    if g: print(f"   live combined {lo_:.1f}-{hi_:.1f}: n {len(g):3d}, pay/line median {np.median(g):.2f} (min {min(g):.2f})")
pay_lo = sorted(non, key=lambda u: E[u])[:12]
print("12 lowest-paid unprotected: (uid, age d, pay/line, live combined):", [(u, round(age[u], 1), round(E[u] / line, 2), round(c.get(u, 0), 3)) for u in pay_lo])
