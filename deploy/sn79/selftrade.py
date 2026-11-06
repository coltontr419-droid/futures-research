import json
ours = [l.split() for l in open("/opt/mvtrx/our_uids.txt") if l.strip()]
makers = {int(u) for u, r, *_ in ours if r == "maker"}; takers = {int(u) for u, r, *_ in ours if r == "taker"}
n = x = 0
with open("/opt/mvtrx/live_tape_x1.jsonl") as fh:
    fh.seek(0, 2); fh.seek(max(0, fh.tell() - 200_000_000)); fh.readline()
    for l in fh:
        if '"Ma": ' not in l: continue
        r = json.loads(l)
        if r.get("Ma") in makers:
            n += 1
            if r.get("Ta") in takers: x += 1
print("our makers %s fills in the last ~200 MB: %d | self-trades (our takers %s taking them): %d" % (sorted(makers), n, sorted(takers), x))
