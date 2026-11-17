import json, urllib.request, urllib.parse, collections, bittensor as bt
A = "https://api.theminos.ai"
def get(p): return json.load(urllib.request.urlopen(urllib.request.Request(A + p, headers={"User-Agent": "curl/8.5.0"}), timeout=40))
m = bt.Subtensor(network="finney").metagraph(107, lite=True); hk2ck = dict(zip(m.hotkeys, m.coldkeys))
rounds = [r for r in get("/scoring/rounds?limit=30")["rounds"] if r["identity_revealed"]][:15]
same_ck_as_better = other = 0; zero_rows = paid_rows = 0; why = collections.Counter()
for r in rounds:
    lb = get(f"/scoring/rounds/{urllib.parse.quote(r['round_id'])}/leaderboard")
    E = sorted([e for e in lb["entries"] if e.get("status") == "scored" and e.get("current_score") is not None], key=lambda e: -e["current_score"])[:20]
    seen = set()
    for e in E:
        ck = hk2ck.get(e["hotkey"], "?"); paid = (e.get("weight") or 0) > 0
        if e.get("eligible") and not paid:
            zero_rows += 1; why["coldkey already paid higher" if ck in seen else "coldkey NOT seen higher"] += 1
        elif paid: paid_rows += 1
        if paid: seen.add(ck)
print(f"{len(rounds)} rounds, top-20 eligible: paid {paid_rows}, zero {zero_rows} -> {dict(why)}")
