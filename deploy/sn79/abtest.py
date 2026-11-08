"""§1316 (rebuilt; the §1307 original was never saved): fill-level A/B — dollar-weighted edge and KEPT bp per maker fill (book mid at the prior second vs fill
price; kept = mid 20 s later), per book group, with a 1-sim-minute block bootstrap of the A − B difference.
python3 abtest.py <tape> <T0 sim s> <T1 sim s> <A=uids> <B=uids>"""
import json, sys, collections, random, statistics as stt
tape, T0, T1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
G = [(a.split("=")[0], {int(u) for u in a.split("=")[1].split(",")}) for a in sys.argv[4:6]]
who = {u: g for g, us in G for u in us}
SN = collections.defaultdict(dict); F = []
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 60000 or t < T0 - 5 or t > T1 + 30: continue
    if b'"Mi"' in l:
        r = json.loads(l)
        if r["Ma"] in who and r["Ma"] != r["Ta"] and T0 <= t < T1: F.append((t, r["book"], r["p"], r["q"], r["s"], who[r["Ma"]]))
    elif b'"bids"' in l:
        r = json.loads(l)
        if r["bids"] and r["asks"]: SN[r["book"]][int(t)] = (r["bid"] + r["ask"]) / 2
rows = []
for t, b, p, q, s, g in F:
    m0 = SN[b].get(int(t) - 1) or SN[b].get(int(t) - 2); m1 = SN[b].get(int(t) + 20)
    if m0 is None or m1 is None: continue
    sg = 1 if s == 1 else -1
    rows.append((g, "$300" if b < 63 else "calm" if b < 102 else "4-dec", int(t // 60), p * q, sg * (m0 - p) / m0 * 1e4, sg * (m1 - p) / m0 * 1e4))
def wm(v, k): d = sum(x[3] for x in v); return sum(x[3] * x[k] for x in v) / d if d else float("nan")
rng = random.Random(7)
for grp in ("$300", "calm", "4-dec"):
    va = [x for x in rows if x[0] == G[0][0] and x[1] == grp]; vb = [x for x in rows if x[0] == G[1][0] and x[1] == grp]
    if len(va) < 10 or len(vb) < 10: continue
    ba = collections.defaultdict(list); bb = collections.defaultdict(list)
    for x in va: ba[x[2]].append(x)
    for x in vb: bb[x[2]].append(x)
    la, lb = list(ba.values()), list(bb.values()); d = []
    for _ in range(1000):
        sa = [y for blk in (rng.choice(la) for _ in la) for y in blk]; sb = [y for blk in (rng.choice(lb) for _ in lb) for y in blk]
        d.append(wm(sa, 5) - wm(sb, 5))
    se = stt.pstdev(d); diff = wm(va, 5) - wm(vb, 5)
    print(f"{grp:5s}: {G[0][0]} {len(va)} fills edge {wm(va, 4):+.2f} KEPT {wm(va, 5):+.2f} bp | {G[1][0]} {len(vb)} fills edge {wm(vb, 4):+.2f} KEPT {wm(vb, 5):+.2f} bp"
          f" | kept diff {diff:+.2f} ± {se:.2f} → {abs(diff) / se:.1f} noise widths")
