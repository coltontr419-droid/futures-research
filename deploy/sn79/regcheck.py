"""Fresh chain registration check: python regcheck.py <hk>=<uid> ...  Prints one line per hotkey; EXITS 1 if any is not registered (§1327: a deploy
one-liner printed NOT REGISTERED and restarted anyway — gate restarts with `regcheck.py ... || exit 1`)."""
import bittensor as bt, json, sys
m = bt.Subtensor(network="finney").metagraph(79, lite=True); bad = 0
for hk, uid in (a.split("=") for a in sys.argv[1:]):
    ss = json.load(open(f"/root/.bittensor/wallets/main/hotkeys/{hk}"))["ss58Address"]
    ok = m.hotkeys[int(uid)] == ss; bad += not ok
    print(hk, uid, "REGISTERED" if ok else "NOT REGISTERED")
sys.exit(1 if bad else 0)
