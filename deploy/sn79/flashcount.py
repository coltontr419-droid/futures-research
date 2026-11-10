"""§1355: flash dislocations on all books — count, size, duration, and how much of the fleet's / x3's making profit (kept bp × $) comes from them.
Event = the book mid moves ≥ X% away from its 300-sim-s median and comes back within 600 sim s.  python3 flashcount.py <tape> <T0> <T1> <X%> fleet=.. us=.."""
import json, sys, collections, statistics as stt
tape, T0, T1, X = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]) / 100
G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[5:7]}; who = {u: g for g, us in G.items() for u in us}
M = collections.defaultdict(dict); F = []
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 90000 or t < T0 - 300 or t > T1 + 30: continue
    if b'"bids"' in l:
        r = json.loads(l)
        if r["bids"] and r["asks"]: M[r["book"]][int(t)] = (r["bid"] + r["ask"]) / 2
    elif b'"Mi"' in l:
        r = json.loads(l)
        if r["Ma"] in who and r["Ma"] != r["Ta"] and T0 <= t < T1: F.append((t, r["book"], r["p"], r["q"], r["s"], who[r["Ma"]]))
ev = []                                                     # (book, start, end, peak deviation)
for b, mm in M.items():
    ts = sorted(mm); i = 0
    while i < len(ts):
        t = ts[i]
        if t < T0 or t >= T1: i += 1; continue
        ref = stt.median([mm[s] for s in ts[max(0, i - 300):i]] or [mm[t]])
        dev = (mm[t] - ref) / ref
        if abs(dev) >= X:
            j = i; peak = dev
            while j < len(ts) and ts[j] - t < 600 and abs((mm[ts[j]] - ref) / ref) >= X / 3:
                peak = max(peak, (mm[ts[j]] - ref) / ref, key=abs); j += 1
            ev.append((b, t, ts[min(j, len(ts) - 1)], peak)); i = j + 1
        else: i += 1
print(f"window sim {T0:.0f}-{T1:.0f} ({(T1 - T0) / 3600:.1f} sim h ≈ {(T1 - T0) / 782:.1f} wall h), threshold {X:.1%}: {len(ev)} events on {len({e[0] for e in ev})} books")
grp = lambda b: "$300" if b < 63 else "calm" if b < 102 else "4-dec"
print("   by group:", dict(collections.Counter(grp(e[0]) for e in ev)), "| median |peak| {:.1%}".format(stt.median([abs(e[3]) for e in ev])) if ev else "")
print("   largest:", [(e[0], int(e[1]), f"{e[3]:+.1%}", int(e[2] - e[1])) for e in sorted(ev, key=lambda e: -abs(e[3]))[:8]])
inev = lambda b, t: any(e[0] == b and e[1] - 30 <= t <= e[2] + 30 for e in ev)
for g in G:
    tot = evp = 0.0; nev = 0
    for t, b, p, q, s, gg in F:
        if gg != g: continue
        m0 = M[b].get(int(t) - 1); m1 = M[b].get(int(t) + 20)
        if m0 is None or m1 is None: continue
        prof = (1 if s == 1 else -1) * (m1 - p) * q
        tot += prof
        if inev(b, t): evp += prof; nev += 1
    print(f"{g:6s}: making profit (kept × size) ${tot:,.0f}; inside events ${evp:,.0f} ({evp / tot if tot else 0:.0%}) from {nev} fills")
