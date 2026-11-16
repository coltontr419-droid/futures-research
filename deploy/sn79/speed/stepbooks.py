"""Books filled by 255 per class with vs without behind (deep) fills, and behind-fill depth distribution with markouts."""
import json, sys, collections
tape, LO, HI, U = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
S = collections.defaultdict(dict); F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0: continue
    ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    if s < LO - 5 or s > HI + 65: continue
    j = l.find(b'"book": ')
    if j < 0: continue
    bk = int(l[j + 8:l.index(b",", j)])
    if bk >= 192: continue
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask"): S[bk][s] = (r["bid"], r["ask"])
    elif b'"Ta"' in l:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen: continue
        seen.add(k)
        if r.get("Ma") == U and LO <= s < HI: F.append((s, bk, r["p"], r["q"], r["s"]))
allb = collections.defaultdict(set); stepb = collections.defaultdict(set); D = collections.defaultdict(lambda: [0, 0.0, 0.0])
for s, bk, p, q, side in F:
    c = "$300" if bk < 128 else "$30"; allb[c].add(bk)
    a = S[bk].get(s - 1); b = S[bk].get(s + 60)
    if not a: continue
    buy = side == 1; tick = 0.01
    d = round(((a[0] - p) if buy else (p - a[1])) / tick)
    if d <= 0: stepb[c].add(bk)
    elif c == "$300" and b:
        m0 = (a[0] + a[1]) / 2; mo = (1 if buy else -1) * ((b[0] + b[1]) / 2 - m0) / m0 * 1e4
        bb = "1-4" if d <= 4 else ("5-9" if d <= 9 else ("10-19" if d <= 19 else "20+"))
        x = D[bb]; x[0] += 1; x[1] += p * q; x[2] += p * q * mo
for c in ("$300", "$30"):
    print(f"{c}: books filled {len(allb[c])} | with inside/touch fills {len(stepb[c])}")
for bb in ("1-4", "5-9", "10-19", "20+"):
    x = D[bb]
    if x[0]: print(f"  $300 behind depth {bb:5s} ticks: n {x[0]:4d} ${x[1]/1e3:5.0f}k mo60 {x[2]/x[1]:+.2f} bp")
