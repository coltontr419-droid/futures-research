"""MEASURED: where do our $300 BEHIND-the-touch fills come from? For each of our maker fills, find the order's first appearance in our queue lines
(price + the touch at that second) → placement depth: 'placed inside/at touch' vs 'placed as ladder (behind)'. Split by calm (63-101) / vol books."""
import json, sys, collections
tape, LO, HI, U = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
S = collections.defaultdict(dict); first = {}; F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0 or b'"book": ' not in l: continue
    try: ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    except ValueError: continue
    if s < LO - 120 or s > HI + 25: continue
    j = l.find(b'"book": '); bk = int(l[j + 8:l.index(b",", j)])
    if bk >= 128: continue
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask"): S[bk][s] = (r["bid"], r["ask"])
    elif b'"queue"' in l[:90]:
        for q in json.loads(l)["queue"]:
            if (bk, q[4]) not in first: first[(bk, q[4])] = (s, q[0], q[1])
    elif b'"Ma"' in l:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen: continue
        seen.add(k)
        if r.get("Ma") == U and LO <= s < HI: F.append((s, bk, r["p"], r["q"], r["s"], r.get("Mi")))
R = collections.defaultdict(lambda: [0.0, 0.0, 0]); tot = 0.0
for s, bk, p, q, side, mi in F:
    a = S[bk].get(s - 1); b = S[bk].get(s + 20)
    if not (a and b): continue
    buy = side == 1; sg = 1 if buy else -1; m0 = (a[0] + a[1]) / 2
    d = round(((a[0] - p) if buy else (p - a[1])) / 0.01)
    if d < 1: continue
    fr = first.get((bk, mi)); grp = "calm" if 63 <= bk <= 101 else "vol"
    if fr is None: src = "unseen (placed & filled < 1 s)"
    else:
        t0, sd, px = fr; tp = S[bk].get(t0) or S[bk].get(t0 - 1)
        if not tp: src = "no book at placement"
        else:
            pd_ = round(((tp[0] - px) if sd == 0 else (px - tp[1])) / 0.01)
            src = "placed at/inside touch, left behind" if pd_ <= 0 else ("ladder 1-2 ticks back" if pd_ <= 2 else "ladder 3+ ticks back")
    mo = sg * ((b[0] + b[1]) / 2 - m0) / m0 * 1e4; x = R[(grp, src)]; x[0] += p * q; x[1] += p * q * mo; x[2] += 1; tot += p * q
print(f"== uid {U}: $300 BEHIND-touch fills by source (share of ALL behind $, n, 20-s markout bp)")
for k in sorted(R, key=lambda k: -R[k][0]):
    v = R[k]; print(f"  {k[0]:4} | {k[1]:38} {v[0] / tot:4.0%}  n {v[2]:5d}  mo {v[1] / v[0]:+.2f}")
