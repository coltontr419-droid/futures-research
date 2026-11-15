"""MEASURED: age of the maker ORDER at fill, for $300 inside/touch fills. Order ids are global and increase with time: our own queue lines give (id, first-seen sec)
pairs → a monotone id→time map (lower envelope); a fill's maker order id (Mi) → its placement time ≈ map(Mi). age = fill sec − placement sec."""
import json, sys, collections, bisect
tape, LO, HI = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]; US = set(U)
S = collections.defaultdict(dict); F = []; seen = set(); first = {}
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0: continue
    ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    if s < LO - 400 or s > HI + 25: continue
    j = l.find(b'"book": '); bk = int(l[j + 8:l.index(b",", j)])
    if b'"queue"' in l[:90]:
        for q in json.loads(l)["queue"]:
            if (bk, q[4]) not in first: first[(bk, q[4])] = s
        continue
    if bk >= 128: continue
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask"): S[bk][s] = (r["bid"], r["ask"])
    elif b'"Ta"' in l:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen: continue
        seen.add(k)
        if r.get("Ma") in US and LO <= s < HI and r.get("Mi") is not None: F.append((s, bk, r["Ma"], r["p"], r["q"], r["s"], r["Mi"]))
per = collections.defaultdict(list)
for (bk, oid), t in first.items(): per[bk].append((oid, t))
MAP = {}
for bk, pts in per.items():             # per book: lower envelope — an id was placed no later than the earliest time any id >= it was seen
    pts.sort(); ids = []; tms = []; best = 10 ** 18
    for oid, t in reversed(pts):
        best = min(best, t); ids.append(oid); tms.append(best)
    ids.reverse(); tms.reverse(); MAP[bk] = (ids, tms)
def placed(bk, oid):
    if bk not in MAP: return None
    ids, tms = MAP[bk]; k = bisect.bisect_left(ids, oid)
    return tms[k] if k < len(ids) else None
B = [(0, 1), (1, 3), (3, 10), (10, 30), (30, 10 ** 9)]
R = collections.defaultdict(lambda: [0.0, 0.0, 0]); TOT = collections.defaultdict(float)
for s, bk, u, p, q, side, mi in F:
    a = S[bk].get(s - 1); b = S[bk].get(s + 20); t0 = placed(bk, mi)
    if not (a and b) or t0 is None: continue
    buy = side == 1; sg = 1 if buy else -1; m0 = (a[0] + a[1]) / 2
    d = round(((a[0] - p) if buy else (p - a[1])) / 0.01); kind = "inside" if d < 0 else ("touch" if d == 0 else "behind")
    mo = sg * ((b[0] + b[1]) / 2 - m0) / m0 * 1e4; age = max(0, s - t0)
    bb = next(f"{lo}-{hi if hi < 10**9 else '+'}s" for lo, hi in B if lo <= age < hi)
    grp = "calm" if 63 <= bk <= 101 else "vol"
    for kk in (kind, "all", "all-" + grp):
        x = R[(u, kk, bb)]; x[0] += p * q; x[1] += p * q * mo; x[2] += 1; TOT[(u, kk)] += p * q
print(f"id→time map from {len(first)} of our order ids")
for kind in ("all-vol", "all-calm"):
    print(f"== $300 {kind.upper()} fills by ORDER AGE at fill (share of $, n, 20-s markout bp)")
    for u in U:
        print(f"  {u}: " + " | ".join(f"{bb} {R[(u, kind, bb)][0] / max(TOT[(u, kind)], 1e-9):3.0%} n{R[(u, kind, bb)][2]} {R[(u, kind, bb)][1] / R[(u, kind, bb)][0]:+.2f}" for bb in [f"{lo}-{hi if hi < 10**9 else '+'}s" for lo, hi in B] if R[(u, kind, bb)][0]))
