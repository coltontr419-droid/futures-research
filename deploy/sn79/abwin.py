"""§1342: A/B over alternating windows on ONE miner (live switches, no restarts): per window the fleet − us kept gap per book group; pooled A vs B with a
window-level bootstrap.  python3 abwin.py <tape> <switch log> fleet=<uids> us=<uid>   (log lines: 'HH:MM:SS sim <s> <label> <json>'; label A/B/END)"""
import json, sys, collections, random, statistics as stt
tape, logf = sys.argv[1], sys.argv[2]; G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[3:5]}
who = {u: g for g, us in G.items() for u in us}
W = [(int(l.split()[2]), l.split()[3]) for l in open(logf) if " sim " in l]
wins = [(W[i][0], W[i + 1][0], W[i][1]) for i in range(len(W) - 1) if W[i][1] in ("A", "B")]
T0, T1 = wins[0][0], wins[-1][1]; SN = collections.defaultdict(dict); F = []
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 60000 or t < T0 - 5 or t > T1 + 30: continue
    j = l.find(b'"book": '); b = int(l[j + 8:l.index(b",", j)])
    if b'"Mi"' in l:
        r = json.loads(l)
        if r["Ma"] in who and r["Ma"] != r["Ta"] and T0 <= t < T1: F.append((t, b, r["p"], r["q"], r["s"], who[r["Ma"]]))
    elif b'"bids"' in l:
        r = json.loads(l)
        if r["bids"] and r["asks"]: SN[b][int(t)] = (r["bid"] + r["ask"]) / 2
cell = collections.defaultdict(lambda: [0.0, 0.0, 0])
for t, b, p, q, s, g in F:
    m0 = SN[b].get(int(t) - 1); m1 = SN[b].get(int(t) + 20)
    if m0 is None or m1 is None: continue
    k = (1 if s == 1 else -1) * (m1 - p) / m0 * 1e4; grp = "$300" if b < 63 else "calm" if b < 102 else "4-dec"
    wi = next((i for i, (a, z, _) in enumerate(wins) if a <= t < z), None)
    if wi is None: continue
    c = cell[(wi, grp, g)]; c[0] += k * p * q; c[1] += p * q; c[2] += 1
rng = random.Random(5)
rows = collections.defaultdict(list)                     # (lab, grp, g) -> [(block, usd, kept)]  — fill level, 1-sim-min blocks
for t, b, p, q, s_, g in F:
    m0 = SN[b].get(int(t) - 1); m1 = SN[b].get(int(t) + 20)
    if m0 is None or m1 is None: continue
    wi = next((i for i, (a_, z, _) in enumerate(wins) if a_ <= t < z), None)
    if wi is None: continue
    grp = "$300" if b < 63 else "calm" if b < 102 else "4-dec"
    rows[(wins[wi][2], grp, g)].append((int(t // 60), p * q, (1 if s_ == 1 else -1) * (m1 - p) / m0 * 1e4))
def kept(v): d = sum(x[1] for x in v); return sum(x[1] * x[2] for x in v) / d if d else float("nan")
def boot(v):
    bl = collections.defaultdict(list)
    for x in v: bl[x[0]].append(x)
    L = list(bl.values()); return [y for blk in (rng.choice(L) for _ in L) for y in blk]
for grp in ("$300", "calm", "4-dec"):
    for wi, (a_, z, lab) in enumerate(wins):
        f, u = cell.get((wi, grp, "fleet")), cell.get((wi, grp, "us"))
        if f and u and f[1] and u[1]:
            print(f"  {grp:5s} window {wi} [{lab}] sim {a_}-{z}: us kept {u[0] / u[1]:+.2f} (n {u[2]}) fleet {f[0] / f[1]:+.2f} → gap {f[0] / f[1] - u[0] / u[1]:+.2f}")
    k = {key: rows[(key[0], grp, key[1])] for key in (("A", "us"), ("B", "us"), ("A", "fleet"), ("B", "fleet"))}
    if not all(k.values()): continue
    gapA = kept(k[("A", "fleet")]) - kept(k[("A", "us")]); gapB = kept(k[("B", "fleet")]) - kept(k[("B", "us")]); d = gapB - gapA
    bs = []
    for _ in range(1000):
        bs.append((kept(boot(k[("B", "fleet")])) - kept(boot(k[("B", "us")]))) - (kept(boot(k[("A", "fleet")])) - kept(boot(k[("A", "us")]))))
    se = stt.pstdev(bs)
    print(f"== {grp}: pooled gap A {gapA:+.2f} | B {gapB:+.2f} | A closes the gap by {d:+.2f} ± {se:.2f} → {abs(d) / se if se else float('nan'):.1f} widths "
          f"(us kept A {kept(k[('A', 'us')]):+.2f} vs B {kept(k[('B', 'us')]):+.2f}; fill-level 1-sim-min block bootstrap)")
