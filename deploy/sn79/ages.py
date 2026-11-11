import bittensor as bt
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); blk = st.get_current_block()
for u in (48, 178, 119, 117, 5, 146, 216, 64):
    rb = int(st.query_subtensor("BlockAtRegistration", params=[79, u]).value)
    print(f"UID {u:3d}: age {(blk - rb) * 12 / 86400:5.1f} d | coldkey {m.coldkeys[u][:8]} | hotkey {m.hotkeys[u][:8]}")
