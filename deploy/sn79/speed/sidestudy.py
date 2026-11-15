"""MEASURED side study: $300 maker fills that stepped INSIDE (fill price beat the touch of the second before) — 252/216 vs ours.
For each, features at the second before (signed so + = in favour of the maker's side, i.e. predicts price moving the maker's way):
 fund = (fundamental − mid)/mid bp × side; fmv = 5-s change of (fundamental − mid) bp × side; flow = 10-s taker $ toward the opposite side (buyers lifting when the
 maker sells → − ; computed as + when recent takers traded in the direction the maker is positioned after the fill); imb = top-5 depth imbalance × side;
 micro = (microprice − mid)/tick × side; ret5 = 5-s mid return bp × side.
Reports per uid: mean of each feature, share with feature > 0, and markout of fills with feature > 0 vs <= 0 (block-bootstrap ±). python sidestudy.py <tape> lo hi uids..."""
import json, sys, collections, random
tape, LO, HI = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]; US = set(U)
S = collections.defaultdict(dict); TR = collections.defaultdict(list); F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0: continue
    ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    if s < LO - 30 or s > HI + 30: continue
    j = l.find(b'"book": '); bk = int(l[j + 8:l.index(b",", j)])
    if bk >= 128: continue
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask") and r.get("bids") and r.get("asks"): S[bk][s] = (r["bid"], r["ask"], r["bids"], r["asks"], r.get("fund"))
    elif b'"Ta"' in l:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen: continue
        seen.add(k); TR[bk].append((s, 1 if r["s"] == 0 else -1, r["p"] * r["q"]))      # +1 = taker bought
        if r.get("Ma") in US and LO <= s < HI: F.append((s, bk, r["Ma"], r["p"], r["q"], r["s"]))
T = 0.01
def mid(x): return (x[0] + x[1]) / 2
rows = collections.defaultdict(list)
for s, bk, u, p, q, side in F:
    st = S[bk]; a = st.get(s - 1); b = st.get(s + 20); c = st.get(s - 6)
    if not (a and b and c): continue
    buy = side == 1; sg = 1 if buy else -1; m0 = mid(a)
    d = round(((a[0] - p) if buy else (p - a[1])) / T)
    kind = "inside" if d < 0 else ("touch" if d == 0 else "behind")
    mo = sg * (mid(b) - m0) / m0 * 1e4
    f0 = a[4]; fc = c[4]
    fund = sg * (f0 - m0) / m0 * 1e4 if f0 else 0.0
    fmv = sg * (((f0 - m0) - (fc - mid(c))) / m0 * 1e4) if (f0 and fc) else 0.0
    bq = sum(x[1] for x in a[2][:5]); aq = sum(x[1] for x in a[3][:5]); imb = sg * (bq - aq) / (bq + aq) if bq + aq else 0.0
    mp = (a[0] * a[3][0][1] + a[1] * a[2][0][1]) / (a[2][0][1] + a[3][0][1]); micro = sg * (mp - m0) / T
    ret5 = sg * (m0 - mid(c)) / m0 * 1e4
    fl = sum(x[1] * x[2] for x in TR[bk] if s - 10 <= x[0] < s)   # + = takers net buying
    flow = sg * fl / 1e3                                              # + = takers buying while maker BUYS (momentum toward maker's side), $k
    rows[(u, kind)].append(dict(usd=p * q, mo=mo, fund=fund, fmv=fmv, imb=imb, micro=micro, ret5=ret5, flow=flow, s=s))
def boot(v, n=300):
    blocks = collections.defaultdict(list)
    for x in v: blocks[x["s"] // 60].append(x)
    ks = list(blocks); out = []
    for _ in range(n):
        smp = [x for k in random.choices(ks, k=len(ks)) for x in blocks[k]]
        w = sum(x["usd"] for x in smp); out.append(sum(x["usd"] * x["mo"] for x in smp) / w if w else 0)
    out.sort(); return (out[int(.05 * n)], out[int(.95 * n)])
FE = ["fund", "fmv", "imb", "micro", "ret5", "flow"]
for kind in ("inside", "touch"):
    print(f"== $300 {kind.upper()} fills (MEASURED; + feature = favours the maker's side; markout 20 s bp, $-weighted; [5-95% block bootstrap])")
    for u in U:
        v = rows[(u, kind)]
        if len(v) < 20: print(f"  {u}: {len(v)} fills (too few)"); continue
        w = sum(x["usd"] for x in v); m = sum(x["usd"] * x["mo"] for x in v) / w; lo, hi = boot(v)
        line = f"  {u}: n {len(v):4d} mo {m:+5.2f} [{lo:+.2f},{hi:+.2f}] |"
        for f in FE:
            pos = [x for x in v if x[f] > 0]; neg = [x for x in v if x[f] <= 0]
            mp = sum(x["usd"] * x["mo"] for x in pos) / max(sum(x["usd"] for x in pos), 1e-9); mn = sum(x["usd"] * x["mo"] for x in neg) / max(sum(x["usd"] for x in neg), 1e-9)
            line += f" {f} >0 {len(pos) / len(v):3.0%} (mo {mp:+.2f} vs {mn:+.2f}) |"
        print(line)
