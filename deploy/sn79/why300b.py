"""§1326: $300 fills split by HOW the order was placed — vs the own-side best 1 s before ITS placement (inside / joined / behind), whether that best had moved
AWAY in the 10 s before placement (real chasing), and whether the old flow-pull condition was on at the fill. Groups: name=uids@T0-T1.  Read-only.
python3 why300b.py <tape> <name=uids@T0-T1> ..."""
import json, sys, collections, bisect
tape = sys.argv[1]; GR = []
for a in sys.argv[2:]:
    n, rest = a.split("="); us, win = rest.split("@"); t0, t1 = win.split("-"); GR.append((n, {int(u) for u in us.split(",")}, float(t0), float(t1)))
LO = min(g[2] for g in GR); HI = max(g[3] for g in GR); allu = set().union(*[g[1] for g in GR])
SN = collections.defaultdict(dict); OF = collections.defaultdict(dict); F = []; QID = {}
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 60000 or t < LO - 900 or t > HI + 30: continue
    j = l.find(b'"book": '); b = int(l[j + 8:l.index(b",", j)])
    r = json.loads(l)
    if "queue" in r:
        for q in r["queue"]: QID.setdefault((b, q[4]), t)
        continue
    if b >= 63: continue
    if "Mi" in r:
        if r["Ma"] in allu and r["Ma"] != r["Ta"]: F.append((t, b, r["p"], r["q"], r["s"], r["Ma"], r["Mi"]))
    elif "of" in r: OF[b][int(t)] = (r["of"]["nb2"], r["of"]["na2"])
    elif "bids" in r and r["bids"] and r["asks"]: SN[b][int(t)] = (r["bid"], r["ask"])
PB = collections.defaultdict(list)
for (b, k), v in QID.items(): PB[b].append((k, v))
for b in PB: PB[b].sort()
def placed(b, mi):
    v = PB.get(b, []); ids = [x[0] for x in v]; j = bisect.bisect_left(ids, mi)
    if j == 0 or j >= len(v): return None
    (i0, t0), (i1, t1) = v[j - 1], v[j]; return t0 + (t1 - t0) * (mi - i0) / max(1, i1 - i0)
def snap(b, s):
    for k in (0, 1, 2, 3):
        x = SN[b].get(int(s) - k)
        if x: return x
def near(b, s):
    nb = na = 0.0
    for k in range(s - 9, s + 1):
        x = OF[b].get(k)
        if x: nb += x[0]; na += x[1]
    return (nb - na) / (nb + na) if nb + na > 0 else 0.0
T = 0.01
for name, us, t0, t1 in GR:
    rows = []
    for t, b, p, q, s, ma, mi in F:
        if ma not in us or not (t0 <= t < t1): continue
        pt = placed(b, mi); a = snap(b, t - 1); z = SN[b].get(int(t) + 20)
        if pt is None or not a or not z: continue
        pb = snap(b, pt - 1); pb10 = snap(b, pt - 11)
        if not pb or not pb10: continue
        buy = s == 1; sg = 1 if buy else -1; mid = (a[0] + a[1]) / 2
        own = pb[0] if buy else pb[1]; own10 = pb10[0] if buy else pb10[1]
        rel = round(((own - p) if buy else (p - own)) / T)                         # <0 inside, 0 joined, >0 behind (at placement)
        away = round(((own - own10) if buy else (own10 - own)) / T)                 # + = own-side best moved AWAY (up for a bid) in the 10 s before placement
        fp = any((near(b, k) < -0.3) if buy else (near(b, k) > 0.3) for k in range(int(t) - 3, int(t)))
        rows.append(dict(usd=p * q, kept=sg * ((z[0] + z[1]) / 2 - p) / mid * 1e4, edge=sg * (mid - p) / mid * 1e4, move=sg * ((z[0] + z[1]) / 2 - mid) / mid * 1e4,
                         place=("inside" if rel < 0 else "joined the touch" if rel == 0 else "1-4 behind" if rel < 5 else "5+ behind"),
                         chase=("best moved AWAY ≥ 3 ticks before placing" if away >= 3 else "moved away 1-2 ticks" if away >= 1 else "best flat / came toward"),
                         fp=("pull condition ON at fill" if fp else "pull condition off")))
    if not rows: print(f"\n== {name}: no rows"); continue
    D = sum(x["usd"] for x in rows); w = lambda v, k: sum(x[k] * x["usd"] for x in v) / sum(x["usd"] for x in v)
    print(f"\n== {name} ({len(rows)} $300 fills, sim {t0:.0f}-{t1:.0f}): kept {w(rows, 'kept'):+.2f} = edge {w(rows, 'edge'):+.2f} + move {w(rows, 'move'):+.2f}")
    print("   -- placement x chasing:")
    for c in sorted({x["chase"] for x in rows}):
        for pl in ("inside", "joined the touch", "1-4 behind", "5+ behind"):
            v = [x for x in rows if x["chase"] == c and x["place"] == pl]
            if len(v) >= 5: print(f"   {c[:24]:24s} | {pl:16s} {sum(x['usd'] for x in v) / D:4.0%} of $ | kept {w(v, 'kept'):+5.2f} (move {w(v, 'move'):+5.2f}) n {len(v)}")
    for dim in ("place", "chase", "fp"):
        for k in sorted({x[dim] for x in rows}):
            v = [x for x in rows if x[dim] == k]
            print(f"   {k:42s} {sum(x['usd'] for x in v) / D:4.0%} of $ | kept {w(v, 'kept'):+5.2f} (edge {w(v, 'edge'):+5.2f}, move {w(v, 'move'):+5.2f}) n {len(v)}")
