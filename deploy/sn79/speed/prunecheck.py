import json, urllib.request, bittensor as bt, numpy as np
tao = json.load(urllib.request.urlopen(urllib.request.Request("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", headers={"User-Agent": "curl/8.5.0"}), timeout=20))["bittensor"]["usd"]
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); b = st.get_current_block()
tempo = st.query_subtensor("Tempo", params=[79]).value; imm = st.query_subtensor("ImmunityPeriod", params=[79]).value; alpha = float(st.subnet(79).price)
E = np.array(m.emission, dtype=float) * (7200 / (tempo + 1)) * alpha * tao * 30
rb = {u: int(st.query_subtensor("BlockAtRegistration", params=[79, u]).value) for u in range(256)}
vt = np.array(m.validator_trust, dtype=float)
non = [u for u in range(1, 256) if b - rb[u] >= imm]
ours = {85: "x2", 47: "x1", 54: "x3", 228: "x4"}
print(f"immunity {imm} blocks ≈ {imm*12/3600:.1f} h; non-immune UIDs {len(non)}")
for u in ours: print(f"  ours {u} ({ours[u]}): ${E[u]:.0f}/mo, immunity ends in {(imm - (b - rb[u]))*12/3600:+.1f} h")
srt = sorted(non, key=lambda u: E[u])
print("lowest 15 non-immune UIDs (prune order):", [(u, round(E[u]), "VAL" if vt[u] > 0 else "") for u in srt[:15]])
for u, lab in ((85, "85 at $%.0f" % E[85]), (47, "47 at $%.0f" % E[47])):
    print(f"  non-immune UIDs paid LESS than {lab}: {sum(1 for x in non if E[x] < E[u])} (of which < $20: {sum(1 for x in non if E[x] < 20)})")
# registrations in the last 24 h (= prune events when the subnet is full)
recent = sorted((b - rb[u]) * 12 / 3600 for u in range(256) if b - rb[u] < 7200)
print(f"UIDs registered in the last 24 h: {len(recent)} (≈ prunes per day when full)")
soon = sorted([u for u in range(1, 256) if 0 <= imm - (b - rb[u]) <= 1800 and u not in ours], key=lambda u: imm - (b - rb[u]))
print("UIDs leaving immunity in the next 6 h (ends in h, pay):", [(u, round((imm - (b - rb[u])) * 12 / 3600, 1), round(E[u])) for u in soon])
print("  of these, paid below $93:", sum(1 for u in soon if E[u] < 93), "| below $103:", sum(1 for u in soon if E[u] < 103))
