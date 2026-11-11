import json
# our_uids.txt: "<uid> <maker|taker> <name> [start sim s]" — fills before a UID's start sim s belong to its previous owner (§1250)
ours = [l.split() for l in open("/opt/mvtrx/our_uids.txt") if l.strip()]
since = {int(p[0]): float(p[3]) if len(p) > 3 else 0.0 for p in ours}
makers = {int(p[0]) for p in ours if p[1] == "maker"}; takers = {int(p[0]) for p in ours if p[1] == "taker"}
n = x = 0
with open("/opt/mvtrx/live_tape_x3.jsonl") as fh:
    fh.seek(0, 2); fh.seek(max(0, fh.tell() - 200_000_000)); fh.readline()
    for l in fh:
        if '"Ma": ' not in l: continue
        r = json.loads(l)
        if r.get("Ma") in makers:
            n += 1
            t = r["ts"] / 1e9
            ta = r.get("Ta")
            if ta in since and ta != r.get("Ma") and t >= since[ta] and t >= since[r["Ma"]]: x += 1   # §1390: ANY two of our UIDs (maker-maker too)
print("our makers %s fills in the last ~200 MB: %d | self-trades (any two of our UIDs, takers %s): %d" % (sorted(makers), n, sorted(takers), x))
