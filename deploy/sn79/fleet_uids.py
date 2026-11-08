import bittensor as bt
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); blk = st.get_current_block()
out = []
for u in range(len(m.coldkeys)):
    if m.coldkeys[u].startswith("5F1F2JMu"):
        rb = int(st.query_subtensor("BlockAtRegistration", params=[79, u]).value)
        out.append((u, round((blk - rb) * 12 / 86400, 1)))
print(",".join(str(u) for u, a in out)); print(sorted(a for u, a in out))
