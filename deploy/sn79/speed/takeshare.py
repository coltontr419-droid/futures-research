"""MEASURED: per uid, maker vs taker $ by book class over a sim window; and the 20-s markout of its TAKER trades (+ = price moved its way after it took)."""
import json, sys, collections
tape, LO, HI = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]; US = set(U)
S = collections.defaultdict(dict); T = []; seen = set(); V = collections.defaultdict(float)
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0 or b'"book": ' not in l: continue
    try: ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    except ValueError: continue
    if s < LO - 5 or s > HI + 25: continue
    j = l.find(b'"book": '); bk = int(l[j + 8:l.index(b",", j)])
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask"): S[bk][s] = (r["bid"], r["ask"])
    elif b'"Ta"' in l:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen or not (LO <= s < HI): continue
        seen.add(k); c = "$300" if bk < 128 else ("$30" if bk < 192 else "4dec"); usd = r["p"] * r["q"]
        if r.get("Ma") in US: V[(r["Ma"], c, "maker")] += usd
        if r.get("Ta") in US: V[(r["Ta"], c, "taker")] += usd; T.append((s, bk, r["Ta"], r["s"], usd, c))
M = collections.defaultdict(lambda: [0.0, 0.0])
for s, bk, u, side, usd, c in T:
    a = S[bk].get(s - 1); b = S[bk].get(s + 20)
    if not (a and b): continue
    sg = 1 if side == 0 else -1; m0 = (a[0] + a[1]) / 2   # side 0 = taker bought
    M[(u, c)][0] += usd; M[(u, c)][1] += usd * sg * ((b[0] + b[1]) / 2 - m0) / m0 * 1e4
for u in U:
    parts = []
    for c in ("$300", "$30", "4dec"):
        mk, tk = V[(u, c, "maker")], V[(u, c, "taker")]
        if mk + tk == 0: continue
        mo = M[(u, c)][1] / M[(u, c)][0] if M[(u, c)][0] else float("nan")
        parts.append(f"{c}: maker ${mk / 1e3:6.0f}k taker ${tk / 1e3:6.0f}k ({tk / (mk + tk):4.0%} taker, taker 20-s markout {mo:+.2f})")
    print(f"  {u}: " + " | ".join(parts))
