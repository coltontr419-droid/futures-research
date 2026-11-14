"""Quoting profile per uid per class from the tape (last N sim min, current sim): maker fills, $/book/hour, fill size, depth behind the touch,
mid-to-mid markout (what skill pays) at 20 s / 120 s / 600 s, inventory ($ mean |inv| per book, max) and turnover.   python profile.py <tape> <min> uids..."""
import json, sys, bisect
from collections import defaultdict
tape, LO, HI = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); last = (HI - LO) / 60; U = [int(u) for u in sys.argv[4:]]; US = set(U)
mids = defaultdict(list); tops = defaultdict(list); fills = []; tmax = 0; seen = set()
for line in open(tape):
    i = line.find('"ts": ')
    if i < 0: continue
    ts = int(line[i + 6:line.index(",", i)])
    if ts >= 40000 * 10 ** 9: continue
    if '"bid": ' in line:
        r = json.loads(line)
        if r.get("bid") and r.get("ask"): b = r["book"]; mids[b].append(ts); tops[b].append((r["bid"], r["ask"]))
    elif '"Ma"' in line:
        r = json.loads(line); tmax = max(tmax, ts)
        if r["Ma"] in US:
            k = (r["book"], r.get("id"), ts)
            if k not in seen: seen.add(k); fills.append((ts, r["book"], r["Ma"], r["p"], r["q"], r["s"]))
t0 = LO * 1e9; t1 = HI * 1e9; hours = last / 60 * (1 / 0.16)   # sim min -> wall-ish hours not used; report per sim hour
def cls(b): return 0 if b < 128 else (1 if b < 192 else 2)
def top_at(b, t):
    k = bisect.bisect_right(mids[b], t) - 1
    return tops[b][k] if k >= 0 else None
D = defaultdict(lambda: [0.0, 0.0, 0.0]); S = defaultdict(lambda: defaultdict(float)); inv = defaultdict(float); invsum = defaultdict(float); invmax = defaultdict(float); books = defaultdict(set)
fills.sort()
for ts, b, u, p, q, s in fills:
    if ts < t0 or ts >= t1: continue
    tp = top_at(b, ts - 1)
    if not tp: continue
    c = cls(b); x = S[(u, c)]; buy = s == 1; sg = 1 if buy else -1; m0 = (tp[0] + tp[1]) / 2
    tick = 0.01 if c < 2 else 0.0001
    d = round(((tp[0] - p) if buy else (p - tp[1])) / tick); d = max(-1, min(d, 3))
    x["n"] += 1; x["usd"] += p * q; x[f"d{d}"] += p * q; books[(u, c)].add(b)
    for T in (20, 120, 600):
        t2 = top_at(b, ts + T * 1e9)
        if t2: x[f"m{T}"] += sg * ((t2[0] + t2[1]) / 2 - m0) / m0 * 1e4 * p * q; x[f"w{T}"] += p * q
    x["edge"] += sg * (m0 - p) / m0 * 1e4 * p * q
    t2 = top_at(b, ts + 20e9)
    if t2: D[(u, c, d)][0] += p * q; D[(u, c, d)][1] += sg * ((t2[0] + t2[1]) / 2 - m0) / m0 * 1e4 * p * q; D[(u, c, d)][2] += sg * (m0 - p) / m0 * 1e4 * p * q
    inv[(u, b)] += sg * q * p; invsum[(u, c)] += abs(inv[(u, b)]); x["k"] += 1
    invmax[(u, c)] = max(invmax[(u, c)], abs(inv[(u, b)]))
simh = last / 60
print(f"last {last:.0f} sim min | per class: $ per book per sim hour, avg fill, % of $ at touch / +1 / +2+, edge at fill vs mid, mid-to-mid markout 20/120/600 s (bp, + = price moved our way), mean |inventory| $ per book at fills, max")
for c, name in enumerate(["$300", "$30", "4dec"]):
    print(f"== {name}")
    for u in U:
        x = S[(u, c)]
        if not x["n"]: print(f"  {u:3d}: no fills"); continue
        v = x["usd"]; nb = len(books[(u, c)])
        mk = " ".join(f"{x[f'm{T}']/x[f'w{T}']:+5.2f}" if x[f'w{T}'] else "  n/a" for T in (20, 120, 600))
        print(f"  {u:3d}: fills {x['n']:5.0f} on {nb:3d} books | ${v/nb/simh/1e3:6.1f}k/book/sim-h | fill ${v/x['n']:5.0f} | touch {100*x['d0']/v:3.0f}% +1 {100*x['d1']/v:3.0f}% +2+ {100*(x['d2']+x['d3'])/v:3.0f}% | "
              f"edge {x['edge']/v:+5.2f} | markout {mk} | |inv| ${invsum[(u,c)]/x['k']/1e3:5.1f}k max ${invmax[(u,c)]/1e3:5.1f}k")
print("== $300 by fill depth (ticks from the touch before the fill): share of $, edge, 20 s markout, kept = edge + markout")
for u in U:
    tot = sum(D[(u, 0, d)][0] for d in range(-1, 4))
    print(f"  {u:3d}: " + " || ".join(f"d{d}: {D[(u,0,d)][0]/tot:4.0%} edge {D[(u,0,d)][2]/D[(u,0,d)][0]:+5.2f} mo20 {D[(u,0,d)][1]/D[(u,0,d)][0]:+5.2f} kept {(D[(u,0,d)][1]+D[(u,0,d)][2])/D[(u,0,d)][0]:+5.2f}" for d in range(-1, 4) if D[(u,0,d)][0]))
