"""§1303: every observable route behind maker quality, x2 vs the long-lived fleet, per book group ($300, calm). For each maker fill: size, depth vs the touch
(inside / touch / 1-2 / 3+ ticks), spread in ticks before the fill, mid move in the 10 s BEFORE the fill against the maker (momentum into the order), the maker's
|inventory| before the fill and whether the fill grows it, and the book. Outcome per bucket: share of $, edge at fill, kept 20 s later (edge + mid move), kept÷edge.
Plus loss concentration: the worst books' share of all negative kept-$.   python fillprobe.py <tape> <since sim s> <name=uid,uid> ...  (until = now)"""
import json, sys, collections, bisect
tape, LO = sys.argv[1], float(sys.argv[2]); G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[3:]}
who = {u: g for g, us in G.items() for u in us}
B = collections.defaultdict(lambda: ([], [], [])); F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 90000 or t < LO - 120: continue
    if b'"bid": ' in l[:80]:
        j = l.find(b'"bids"'); r = json.loads(l[:j].rstrip(b', ') + b"}")
        if r["book"] < 102 and r.get("bid") and r.get("ask"): a = B[r["book"]]; a[0].append(t); a[1].append(r["bid"]); a[2].append(r["ask"])
    elif b'"Ma": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"), r["ts"])
        if k in seen or r["book"] >= 102: continue
        seen.add(k)
        if r.get("Ma") in who: F.append((who[r["Ma"]], r["Ma"], r["book"], t, r["s"], r["q"], r["p"]))
inv = collections.defaultdict(float); R = collections.defaultdict(list); BOOK = collections.defaultdict(float)
for g, u, b, t, s, q, p in sorted(F, key=lambda x: x[3]):
    mk = -1 if s == 0 else 1; before = inv[(u, b)]; inv[(u, b)] += mk * q
    if t < LO: continue
    a = B[b]; i = bisect.bisect_left(a[0], t) - 1; j = bisect.bisect_left(a[0], t + 20); h = bisect.bisect_left(a[0], t - 10)
    if i < 0 or j >= len(a[0]) or h >= len(a[0]): continue
    bid, ask = a[1][i], a[2][i]; m0 = (bid + ask) / 2; m1 = (a[1][j] + a[2][j]) / 2; mb = (a[1][h] + a[2][h]) / 2; tick = 0.01
    best = ask if s == 0 else bid; d = round(((p - best) if s == 0 else (best - p)) / tick); sp = round((ask - bid) / tick)
    edge = mk * (m0 - p) / m0 * 1e4; kept = edge + mk * (m1 - m0) / m0 * 1e4; usd = q * p
    pre = -mk * (m0 - mb) / m0 * 1e4                       # > 0: the mid moved AGAINST the maker's side in the 10 s before (price running into the order)
    grp = "$300" if b < 63 else "calm"
    feats = {"size": "<$1k" if usd < 1000 else "$1-2k" if usd < 2000 else "$2-4k" if usd < 4000 else "$4k+",
             "depth": "inside" if d < 0 else "touch" if d == 0 else "1-2 behind" if d <= 2 else "3+ behind",
             "spread": f"{min(sp, 4)}{'+' if sp >= 4 else ''} ticks",
             "pre-move": "ran INTO us >1bp" if pre > 1 else "ran into us 0-1bp" if pre > 0 else "moved away/flat",
             "|inv| before": "<$2k" if abs(before) * p < 2000 else "$2-6k" if abs(before) * p < 6000 else "$6k+",
             "inventory": "fill GROWS |inv|" if abs(before + mk * q) > abs(before) else "fill shrinks |inv|"}
    for f, v in feats.items(): R[(g, grp, f, v)].append((usd, edge, kept))
    R[(g, grp, "all", "")].append((usd, edge, kept)); BOOK[(g, grp, b)] += usd * kept / 1e4
def row(v, tot):
    w = sum(x[0] for x in v); e = sum(x[0] * x[1] for x in v) / w; k = sum(x[0] * x[2] for x in v) / w
    return f"{w / tot:5.0%} of $ | edge {e:+5.2f} | kept {k:+5.2f} | kept÷edge {k / e if e else 0:+5.2f}"
order = {"size": ["<$1k", "$1-2k", "$2-4k", "$4k+"], "depth": ["inside", "touch", "1-2 behind", "3+ behind"], "spread": ["1 ticks", "2 ticks", "3 ticks", "4+ ticks"],
         "pre-move": ["ran INTO us >1bp", "ran into us 0-1bp", "moved away/flat"], "|inv| before": ["<$2k", "$2-6k", "$6k+"], "inventory": ["fill GROWS |inv|", "fill shrinks |inv|"]}
for grp in ("$300", "calm"):
    print(f"######## {grp} books")
    for g in G:
        allv = R.get((g, grp, "all", ""), [])
        if not allv: continue
        tot = sum(x[0] for x in allv); print(f"== {g}: {len(allv)} fills | {row(allv, tot)}")
        for f, vals in order.items():
            print("   " + f + ": " + " || ".join(f"{v}: {row(R[(g, grp, f, v)], tot)}" for v in vals if R.get((g, grp, f, v))))
        neg = sorted((x for k, x in BOOK.items() if k[0] == g and k[1] == grp and x < 0)); sneg = sum(neg)
        if neg: print(f"   loss concentration: worst 5 books = {sum(neg[:5]) / sneg:.0%} of all negative kept-$ ({len(neg)} books net negative of {sum(1 for k in BOOK if k[0] == g and k[1] == grp)})")
