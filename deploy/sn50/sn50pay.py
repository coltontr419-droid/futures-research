import json, urllib.request, bittensor as bt, numpy as np
tao = json.load(urllib.request.urlopen(urllib.request.Request("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", headers={"User-Agent": "curl/8.5.0"}), timeout=20))["bittensor"]["usd"]
st = bt.Subtensor(network="finney"); n = 50; m = st.metagraph(n, lite=True); b = st.get_current_block()
tempo = st.query_subtensor("Tempo", params=[n]).value; sub = st.subnet(n); alpha = float(sub.price)
E = np.array(m.emission, dtype=float) * (7200 / (tempo + 1)) * alpha * tao * 30
inc = np.array(m.incentive, dtype=float); vt = np.array(m.validator_trust, dtype=float)
miners = [u for u in range(len(E)) if vt[u] == 0]
tot_m = sum(E[u] for u in miners)
print(f"SN50: TAO ${tao:.0f}, alpha {alpha:.5f} TAO, pool tao_in {float(sub.tao_in):,.0f} | UIDs {len(E)} | miner $ total ≈ ${tot_m:,.0f}/mo | all UIDs ${E.sum():,.0f}/mo")
top = sorted(miners, key=lambda u: -E[u])[:15]
ck = list(m.coldkeys)
for u in top:
    print(f"  uid {u:3d} ${E[u]:7,.0f}/mo  incentive {inc[u]:.4f}  share of miner $ {E[u]/tot_m:6.2%}  ck {ck[u][:8]}  age {(b - int(st.query_subtensor('BlockAtRegistration', params=[n, u]).value))*12/86400:.1f} d")
big = sorted(range(len(E)), key=lambda u: -E[u])[:3]
print("largest UIDs overall (incl. owner/validators):", [(u, round(E[u]), round(vt[u], 2)) for u in big])
paid = sorted([E[u] for u in miners if E[u] > 1]); print(f"paid miners {len(paid)}, median ${np.median(paid):.0f}, p90 ${np.percentile(paid, 90):.0f}")
