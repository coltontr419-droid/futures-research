"""§1344: $/month for every UID (earnings_all.py formula: emission × 7200/(tempo+1) × alpha price × TAO price × 30), the fleet (coldkey 5F1F2JMu) by age,
x3, the field and the prune line.  python3 fleetpay.py <tao_usd> <alpha_tao>"""
import bittensor as bt, numpy as np, sys
tao, alpha = float(sys.argv[1]), float(sys.argv[2])
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); blk = st.get_current_block()
tempo = st.query_subtensor("Tempo", params=[79]).value; imm = st.query_subtensor("ImmunityPeriod", params=[79]).value
E = np.array(m.emission, dtype=float); usd = E * (7200 / (tempo + 1)) * alpha * tao * 30
rb = np.array([int(st.query_subtensor("BlockAtRegistration", params=[79, u]).value) for u in range(256)]); age = (blk - rb) * 12 / 86400
non = sorted([u for u in range(1, 256) if blk - rb[u] >= imm], key=lambda u: E[u])
fl = sorted([u for u in range(256) if m.coldkeys[u].startswith("5F1F2JMu")], key=lambda u: -usd[u])
paid = usd[usd > 0]
print(f"tempo {tempo} | TAO ${tao} | alpha {alpha} TAO")
print(f"x3 (UID 64, {age[64] * 24:.1f} h old): ${usd[64]:.0f}/mo")
print(f"prune line (lowest unprotected): ${usd[non[0]]:.0f} | 2nd–5th lowest: {[round(usd[u]) for u in non[1:5]]}")
print(f"field (paid UIDs, n {len(paid)}): p10 ${np.percentile(paid, 10):.0f} | median ${np.median(paid):.0f} | p75 ${np.percentile(paid, 75):.0f} | p90 ${np.percentile(paid, 90):.0f} | max ${paid.max():.0f}")
fv = usd[fl]; print(f"FLEET 5F1F2JMu ({len(fl)} UIDs): total ${fv.sum():,.0f}/mo | top ${fv.max():.0f} | median ${np.median(fv):.0f} | bottom ${fv.min():.0f}")
for lo, hi in ((0, 1), (1, 3), (3, 7), (7, 14), (14, 99)):
    g = [u for u in fl if lo <= age[u] < hi]
    if g: print(f"   age {lo}-{hi} d: {len(g):2d} UIDs  min ${min(usd[u] for u in g):.0f}  median ${np.median([usd[u] for u in g]):.0f}  max ${max(usd[u] for u in g):.0f}")
print("   top 5:", [(u, round(age[u], 1), round(usd[u])) for u in fl[:5]], "| bottom 5:", [(u, round(age[u], 1), round(usd[u])) for u in fl[-5:]])
rank = sorted(range(256), key=lambda u: -usd[u]).index(64) + 1
print(f"x3 rank {rank} of 256 | x3 ÷ fleet median {usd[64] / np.median(fv):.2f} | ÷ fleet bottom {usd[64] / fv.min():.2f} | ÷ prune line {usd[64] / usd[non[0]]:.2f}")
