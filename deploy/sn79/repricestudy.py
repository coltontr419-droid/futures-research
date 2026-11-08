"""§1317: how the long-lived fleet re-prices its CALM-book orders vs ours (tape only). For each maker fill: placement time from the order id (per-book id→time
map built from our own queue records), book state at placement vs at fill: depth vs the own-side best (ticks; <0 inside), the move of the own-side best between
placement and fill (ticks, + = moved AWAY from the order, i.e. the order was left behind), order age, and fill timing per UID-book (gaps between fills).
python3 repricestudy.py <tape> <T0> <T1> fleet=<uids> x4=58 x2=212"""
import json, sys, collections, bisect, statistics as stt
tape, T0, T1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[4:]}; who = {u: g for g, us in G.items() for u in us}
SN = collections.defaultdict(dict); F = []; QID = {}
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 60000 or t < T0 - 700 or t > T1 + 30: continue
    j = l.find(b'"book": '); b = int(l[j + 8:l.index(b",", j)])
    if not (63 <= b < 102): continue
    r = json.loads(l)
    if "Mi" in r:
        if r["Ma"] in who and r["Ma"] != r["Ta"] and T0 <= t < T1: F.append((t, b, r["p"], r["q"], r["s"], r["Ma"], r["Mi"]))
    elif "bids" in r:
        if r["bids"] and r["asks"]: SN[b][int(t)] = (r["bid"], r["ask"])
    elif "queue" in r:
        for q in r["queue"]: QID.setdefault((b, q[4]), t)
PB = collections.defaultdict(list)
for (b, k), v in QID.items(): PB[b].append((k, v))
for b in PB: PB[b].sort()
def placed(b, mi):
    v = PB.get(b, []); ids = [x[0] for x in v]; j = bisect.bisect_left(ids, mi)
    if j == 0 or j >= len(v): return None
    (i0, t0), (i1, t1) = v[j - 1], v[j]; return t0 + (t1 - t0) * (mi - i0) / max(1, i1 - i0)
def snap(b, s):
    for k in (0, 1, 2):
        x = SN[b].get(int(s) - k)
        if x: return x
    return None
T = 0.01; rows = []; last = {}
for t, b, p, q, s, u, mi in sorted(F):
    buy = s == 1; pt = placed(b, mi); a = snap(b, t - 1); z = snap(b, pt) if pt else None
    if not a or not z or pt is None or t - pt < 0: continue
    own_fill = a[0] if buy else a[1]; own_place = z[0] if buy else z[1]
    d_place = round(((own_place - p) if buy else (p - own_place)) / T)        # depth when placed (ticks behind the own-side best; <0 inside)
    d_fill = round(((own_fill - p) if buy else (p - own_fill)) / T)
    away = round(((own_fill - own_place) if buy else (own_place - own_fill)) / T)   # + = best moved away from the order while it rested
    gap = t - last.get((u, b), -1e9); last[(u, b)] = t
    rows.append((who[u], d_place, d_fill, away, t - pt, gap, p * q, (a[1] - a[0]) / T))
def pct(v, k): v = sorted(v); return v[int(len(v) * k)] if v else float("nan")
for g in G:
    v = [x for x in rows if x[0] == g]
    if not v: continue
    D = sum(x[6] for x in v)
    def share(f): return sum(x[6] for x in v if f(x)) / D
    print(f"\n== {g}: {len(v)} calm fills")
    print(f"  placed: inside {share(lambda x: x[1] < 0):.0%} | AT the touch {share(lambda x: x[1] == 0):.0%} | 1 behind {share(lambda x: x[1] == 1):.0%} | 2 {share(lambda x: x[1] == 2):.0%} | 3+ {share(lambda x: x[1] >= 3):.0%}")
    print(f"  at fill: inside {share(lambda x: x[2] < 0):.0%} | touch {share(lambda x: x[2] == 0):.0%} | 1 {share(lambda x: x[2] == 1):.0%} | 2 {share(lambda x: x[2] == 2):.0%} | 3+ {share(lambda x: x[2] >= 3):.0%}")
    print(f"  best moved AWAY from the resting order before the fill: {share(lambda x: x[3] > 0):.0%} of $ (median {pct([x[3] for x in v if x[3] > 0], .5)} ticks) | toward/through it {share(lambda x: x[3] < 0):.0%} | no move {share(lambda x: x[3] == 0):.0%}")
    ag = [x[4] for x in v]; gp = [x[5] for x in v if x[5] < 1e8]
    print(f"  order age at fill: p25 {pct(ag, .25):.0f} median {pct(ag, .5):.0f} p75 {pct(ag, .75):.0f} s | gap since the same UID's previous fill on that book: median {pct(gp, .5):.0f} s, p25 {pct(gp, .25):.0f}, p75 {pct(gp, .75):.0f}")
    print(f"  spread at fill median {pct([x[7] for x in v], .5):.0f} ticks")
