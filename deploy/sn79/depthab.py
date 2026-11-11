"""§1384: x3 fill depth in SPREADS + fill counts + order $ per arm for an A/B switch log (A vs B windows), vs UID 46 (whole tape reference)."""
import json, sys, collections
tape, log = sys.argv[1], sys.argv[2]
W = [l.split() for l in open(log) if " sim " in l]; W = [(int(w[2]), w[3]) for w in W]
wins = [(W[i][0], W[i + 1][0], W[i][1]) for i in range(len(W) - 1) if W[i][1] in ("A", "B")]
lab = lambda t: next((c for a, z, c in wins if a <= t < z), None)
grp = lambda b: "$300" if b < 63 else ("calm" if b < 102 else "4dec")
snap = {}; R = collections.defaultdict(list)
lo = min(a for a, z, c in wins) - 60
for l in open(tape):
    i = l.find('"ts": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(",", i)]) / 1e9
    if t < lo or t >= 90000: continue
    if '"bids"' in l:
        r = json.loads(l); bb = r.get("bids") or []; aa = r.get("asks") or []
        if bb and aa: snap[r["book"]] = (bb[0][0], aa[0][0])
        continue
    if '"Ma": 64' not in l: continue
    c = lab(t)
    if not c: continue
    r = json.loads(l); b = r["book"]; s = snap.get(b)
    if not s or s[1] <= s[0]: continue
    bid = r["s"] == 1; ref = s[0] if bid else s[1]
    R[(grp(b), c)].append((((ref - r["p"]) if bid else (r["p"] - ref)) / (s[1] - s[0]), r["p"] * r["q"]))
q = lambda a, p: sorted(a)[int(p * (len(a) - 1))] if a else float("nan")
ref46 = {"$300": (0.10, 1.0), "calm": (0.33, 1.13), "4dec": (0.17, 1.10)}
for g in ("$300", "calm", "4dec"):
    for c in ("A", "B"):
        v = R[(g, c)]; d = [x[0] for x in v]
        print(f"{g} {c}: fills {len(v):5d} ${sum(x[1] for x in v)/1e3:6.0f}k | depth in spreads median {q(d, .5):+.2f} p75 {q(d, .75):+.2f} p90 {q(d, .9):+.2f} | ahead of touch {100 * sum(x < -0.01 for x in d) / max(len(d), 1):3.0f}% | fill $ median {q([x[1] for x in v], .5):,.0f}"
              + (f"   (UID 46: median {ref46[g][0]:.2f}, p90 {ref46[g][1]:.2f})" if c == "A" else ""))
