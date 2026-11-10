"""§1281: what exactly differs between the long-lived fleet and x3 on the $300 books. (1) depth histogram to 40 ticks (2) 'inside' fills vs the spread in ticks
before the fill (3) inventory: per UID-book |position| in $ at each fill (from all fills on this tape) (4) per side: share of fills that grew vs shrank |inventory|
and net per fill for each.   python fleetx.py <tape> <uids> [since]"""
import json, sys, collections, bisect, statistics as st
tape, U = sys.argv[1], {int(u) for u in sys.argv[2].split(",")}; LO = float(sys.argv[3]) if len(sys.argv) > 3 else 0
B = collections.defaultdict(lambda: ([], [], [])); F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 90000: continue
    if b'"bid": ' in l[:80]:
        j = l.find(b'"bids"'); r = json.loads(l[:j].rstrip(b', ') + b"}")
        if r["book"] < 63 and r.get("bid") and r.get("ask"): a = B[r["book"]]; a[0].append(t); a[1].append(r["bid"]); a[2].append(r["ask"])
    elif b'"Ta": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"))
        if k in seen or r["book"] >= 63: continue
        seen.add(k)
        if r.get("Ma") in U: F.append((r["Ma"], r["book"], t, r["s"], r["q"], r["p"]))
inv = collections.defaultdict(float); D = collections.Counter(); IN = collections.Counter(); POS = []; G = collections.defaultdict(list); n = 0
for u, b, t, s, q, p in sorted(F, key=lambda x: x[2]):
    mk = -1 if s == 0 else 1; before = inv[(u, b)]; inv[(u, b)] += mk * q
    if t < LO: continue
    a = B[b]; i = bisect.bisect_left(a[0], t) - 1
    if i < 0: continue
    bid, ask = a[1][i], a[2][i]; m = (bid + ask) / 2; best = ask if s == 0 else bid
    d = round(((p - best) if s == 0 else (best - p)) / 0.01); D[min(d, 40)] += 1; n += 1
    if d < 0: IN[round((ask - bid) / 0.01)] += 1
    POS.append(abs(before) * p)
    j = bisect.bisect_left(a[0], t + 120)
    if j < len(a[0]):
        m1 = (a[1][j] + a[2][j]) / 2; net = mk * (m - p) / m * 1e4 + mk * (m1 - m) / m * 1e4
        G["grows |inv|" if abs(before + mk * q) > abs(before) else "shrinks |inv|"].append(net)
print(f"fills {n}")
print("depth (ticks behind the touch, −1 = inside), share:", [(k, round(v / n, 3)) for k, v in sorted(D.items()) if v / n >= 0.005])
print("inside fills by the spread in ticks before the fill:", sorted(IN.items())[:10])
print(f"|position| before each fill, $: median {st.median(POS):,.0f}, p75 {sorted(POS)[int(.75 * len(POS))]:,.0f}, p90 {sorted(POS)[int(.9 * len(POS))]:,.0f}")
for k, v in G.items(): print(f"  fills that {k}: {len(v) / n:.0%}, net per fill at 120 s {st.mean(v):+.2f} bp")
