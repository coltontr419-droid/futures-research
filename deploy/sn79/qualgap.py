"""§1292: why does the long-lived fleet keep more of the spread it captures (making quality ≈ 0.75 vs ours ≈ 0.5-0.6)? From maker fills (current sim, since LO sim s):
per group of UIDs and per book group / depth vs the touch / fill size: count, edge at the fill (bp vs the pre-fill mid), mid move 20 s later (the validator's
realized horizon), kept = edge + move20, kept ÷ edge (a quality proxy), and the two-sided share of books (both buy and sell maker volume ≥ 25% of the larger).
    python qualgap.py <tape> <since sim s> <name=uid,uid> [name=uid ...]"""
import json, sys, collections, bisect, statistics as st
tape, LO = sys.argv[1], float(sys.argv[2]); G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[3:]}
who = {u: g for g, us in G.items() for u in us}
B = collections.defaultdict(lambda: ([], [], [])); F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 60000 or t < LO - 60: continue
    if b'"bid": ' in l[:80]:
        j = l.find(b'"bids"'); r = json.loads(l[:j].rstrip(b', ') + b"}")
        if r.get("bid") and r.get("ask"): a = B[r["book"]]; a[0].append(t); a[1].append(r["bid"]); a[2].append(r["ask"])
    elif b'"Ma": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"), r["ts"])
        if k in seen: continue
        seen.add(k)
        if r.get("Ma") in who and t >= LO: F.append((who[r["Ma"]], r["Ma"], r["book"], t, r["s"], r["q"], r["p"]))
grp = lambda b: "$300" if b < 63 else "calm" if b < 102 else "4dec"
R = collections.defaultdict(list); SIDE = collections.defaultdict(lambda: [0.0, 0.0])
for g, u, b, t, s, q, p in F:
    a = B[b]; i = bisect.bisect_left(a[0], t) - 1; j = bisect.bisect_left(a[0], t + 20)
    if i < 0 or j >= len(a[0]): continue
    bid, ask = a[1][i], a[2][i]; m0 = (bid + ask) / 2; m1 = (a[1][j] + a[2][j]) / 2; mk = -1 if s == 0 else 1   # s == 0: maker sold
    tick = 10 ** -max(2, len(str(p).split(".")[-1]) if "." in str(p) else 2)
    best = ask if s == 0 else bid; depth = round(((p - best) if s == 0 else (best - p)) / tick)
    edge = mk * (m0 - p) / m0 * 1e4; mv = mk * (m1 - m0) / m0 * 1e4; usd = q * p
    dk = "inside" if depth < 0 else "touch" if depth == 0 else "1-2 behind" if depth <= 2 else "3+ behind"
    sk = "<$1k" if usd < 1000 else "$1-3k" if usd < 3000 else "$3k+"
    for key in (("all", ""), ("group", grp(b)), ("depth", dk), ("size", sk)): R[(g,) + key].append((usd, edge, mv))
    SIDE[(g, u, b)][0 if mk > 0 else 1] += usd
def row(v):
    w = sum(x[0] for x in v); e = sum(x[0] * x[1] for x in v) / w; m = sum(x[0] * x[2] for x in v) / w
    return f"n {len(v):5d} ${w / 1e3:7,.0f}k | edge {e:+5.2f} bp | mid 20 s later {m:+6.2f} | kept {e + m:+5.2f} | kept÷edge {(e + m) / e if e else 0:+.2f}"
for g in G:
    books = [k for k in SIDE if k[0] == g]; two = sum(1 for k in books if min(SIDE[k]) >= 0.25 * max(SIDE[k]))
    print(f"== {g} ({','.join(map(str, sorted(G[g])))}): two-sided books {two / max(len(books), 1):.0%} of {len(books)} (UID-books)")
    for kind, keys in (("all", [""]), ("group", ["$300", "calm", "4dec"]), ("depth", ["inside", "touch", "1-2 behind", "3+ behind"]), ("size", ["<$1k", "$1-3k", "$3k+"])):
        for k in keys:
            v = R.get((g, kind, k))
            if v: print(f"   {kind:5} {k:10} {row(v)}")
