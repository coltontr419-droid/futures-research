"""MEASURED fill-rate profile per uid ($300 or BOOKS range): fills, $ per fill, books filled, fills per filled book per sim min, share of fills on orders < 1 s old
(per-book order-id → first-seen map from our queue lines), and per-book 'fill streaks' (fills within 10 s of the previous on the same book = sweeps through several orders)."""
import json, sys, collections, bisect, os, statistics as st
tape, LO, HI = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]; US = set(U)
L0, L1 = (int(x) for x in os.environ.get("BOOKS", "0-127").split("-"))
first = {}; F = collections.defaultdict(list); seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0 or b'"book": ' not in l: continue
    try: ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    except ValueError: continue
    if s < LO - 300 or s >= HI: continue
    j = l.find(b'"book": '); bk = int(l[j + 8:l.index(b",", j)])
    if b'"queue"' in l[:90]:
        for q in json.loads(l)["queue"]:
            if (bk, q[4]) not in first: first[(bk, q[4])] = s
    elif b'"Ma"' in l and L0 <= bk <= L1 and s >= LO:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen: continue
        seen.add(k)
        if r.get("Ma") in US: F[r["Ma"]].append((s, bk, r["p"] * r["q"], r.get("Mi")))
per = collections.defaultdict(list)
for (bk, oid), t in first.items(): per[bk].append((oid, t))
MAP = {}
for bk, pts in per.items():
    pts.sort(); ids, tms, best = [], [], 10 ** 18
    for oid, t in reversed(pts): best = min(best, t); ids.append(oid); tms.append(best)
    ids.reverse(); tms.reverse(); MAP[bk] = (ids, tms)
def placed(bk, oid):
    if bk not in MAP or oid is None: return None
    ids, tms = MAP[bk]; k = bisect.bisect_left(ids, oid); return tms[k] if k < len(ids) else None
mins = (HI - LO) / 60
for u in U:
    fs = sorted(F[u])
    if not fs: print(f"  {u}: no fills"); continue
    books = collections.Counter(b for _, b, _, _ in fs); usd = [x[2] for x in fs]
    fresh = sum(1 for s, b, v, mi in fs if (lambda t0: t0 is not None and s - t0 < 1)(placed(b, mi)))
    last = {}; streak = 0
    for s, b, v, mi in fs:
        if b in last and s - last[b] <= 10: streak += 1
        last[b] = s
    print(f"  {u}: fills {len(fs):5d} ${sum(usd) / 1e3:6.0f}k | $/fill median ${st.median(usd):,.0f} mean ${st.mean(usd):,.0f} | books filled {len(books):3d} | fills per filled book per sim min "
          f"{len(fs) / len(books) / mins:.2f} | on orders < 1 s old {fresh / len(fs):.0%} | within 10 s of a previous fill on the book {streak / len(fs):.0%}")
