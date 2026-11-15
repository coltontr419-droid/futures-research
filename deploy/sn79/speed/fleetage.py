import bittensor as bt
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=False); blk = st.get_current_block()
age = lambda u: (blk - int(st.query_subtensor("BlockAtRegistration", params=[79, u]).value)) * 12 / 86400
ck = m.coldkeys[252]
print(f"current block {blk}; UID 252 coldkey {ck[:10]}… hotkey {m.hotkeys[252][:10]}… age {age(252):.2f} days")
ax = m.axons[252]; print("252 axon:", {k: getattr(ax, k, None) for k in ("ip", "port", "version", "protocol", "placeholder1", "placeholder2")})
same = [u for u in range(256) if m.coldkeys[u] == ck]
print(f"UIDs under the same coldkey: {len(same)}")
rows = sorted(((age(u), u, m.axons[u].version, m.axons[u].ip) for u in same), reverse=True)
for a, u, v, ip in rows: print(f"  uid {u:3d} age {a:5.2f} d | axon version {v} | ip {ip}")
