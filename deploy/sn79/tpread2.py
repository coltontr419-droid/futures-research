"""x1 exit + book test read (decisions.md §1261). Only positions OPENED after the test start count. Replays every x1 fill before T1 to get each book's inventory at the start; those positions and the fills that close them are ignored.
Groups, book mod 4: A clock 65 books; B +8 bp no stop 65; C +8 bp no stop + $300; D +4 bp 1 h stop + $300."""
import bisect, json, collections, statistics as st, sys
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_floored, hurdle_filter
T1 = 81009; U = 22
leg = collections.defaultdict(float); ev = collections.defaultdict(list); seen = set(); nleg = 0
for l in open("/opt/mvtrx/live_tape_x1.jsonl", "rb"):
    if b'"bid"' in l[:60]:
        i = l.find(b'"bids"'); r = json.loads(l[:i].rstrip(b', ') + b"}")
        if r["ts"] / 1e9 >= T1 - 30 and r.get("bid") and r.get("ask"): ev[r["book"]].append((r["ts"], 0, (r["bid"] + r["ask"]) / 2))
    elif b'"p"' in l:
        if b'"Ta": 22,' not in l and b'"ts": 8' not in l[:10] and b'"ts": 7' not in l[:10]: continue
        r = json.loads(l); k = (r["book"], r.get("id"), r["ts"]); t = r["ts"] / 1e9
        if k in seen: continue
        if t < T1:
            if r.get("Ta") == U: seen.add(k); leg[r["book"]] += r["q"] if r["s"] == 0 else -r["q"]
        else:
            seen.add(k); ev[r["book"]].append((r["ts"], 1, r))
open0 = sum(abs(v) > 1e-9 for v in leg.values())
G = ("A clock, 65 books", "B +8 no stop, 65", "C +8 no stop, +$300", "D +4 1h, +$300"); A = collections.defaultdict(dict); N = collections.defaultdict(dict); RT = collections.defaultdict(list); OP = collections.defaultdict(list); end = 0; dropped = 0
for b, es in ev.items():
    es.sort(key=lambda e: (e[0], e[1])); g = b % 4; mid = None; L = leg.get(b, 0.0); inv = 0.0; mtm = isum = drift = 0.0; n = 0; notl = 0.0; prev = None; cur = None
    for ts, kind, x in es:
        if kind == 0: mid = x; end = max(end, ts); continue
        p = mid if mid is not None else x["p"]
        if prev is not None and p != prev: mtm += inv * (p - prev); drift += p - prev
        d = x["q"] if x.get("Ta") == U and x["s"] == 0 else (-x["q"] if x.get("Ta") == U else 0.0)
        if d and abs(L) > 1e-9:                         # closes a position from before the test: ignore it
            use = min(abs(d), abs(L)) if d * L < 0 else 0.0
            if use:
                L += d if abs(d) <= abs(L) else -L; dropped += 1; d = d + (use if d < 0 else -use) if abs(d) > use else 0.0
        if d:
            notl += abs(d) * x["p"]
            if abs(inv) * p < 1: cur = (ts, p, 1 if d > 0 else -1); inv = 0.0
        new = inv + d
        if d and cur and abs(new) * p < 1:
            RT[g].append(((ts - cur[0]) / 1e9, cur[2] * (p - cur[1]) / cur[1] * 1e4, b)); cur = None
        inv = new; isum += inv; n += 1; prev = p
    if notl > 0 and n:
        A[g][b] = mtm - isum / n * drift; N[g][b] = notl
        if cur: OP[g].append(((end - cur[0]) / 1e9, cur[2] * ((mid or cur[1]) - cur[1]) / cur[1] * 1e4, b))
print(f"sim min elapsed {(end / 1e9 - T1) / 60:.1f} | books open at the start {open0} | old-position fills ignored {dropped}")
print("group | closed n, mean bp, win | open n, mark bp | all positions mean bp | $300-book positions mean bp, n | books, kept, positive, median α, total α, $")
for g in range(4):
    C = RT[g]; O = OP[g]; c = lambda v: max(-50, min(50, v)); al = [c(x[1]) for x in C] + [c(x[1]) for x in O]; v3 = [c(x[1]) for x in C + O if x[2] < 63]
    k = hurdle_filter({0: A[g]}, {0: N[g]}, 2.3)[0]; bp = sorted(1e4 * A[g][b] / N[g][b] for b in A[g]); tn = sum(N[g].values())
    print(f"{G[g]:20} | {len(C):3d} {st.mean(c(x[1]) for x in C) if C else 0:+6.2f} {sum(x[1] > 0 for x in C) / max(len(C), 1):4.0%} | {len(O):3d} {st.mean(c(x[1]) for x in O) if O else 0:+6.2f} | {st.mean(al) if al else 0:+6.2f} | {st.mean(v3) if v3 else 0:+6.2f} {len(v3):3d} | {len(A[g]):3d} {len(k):3d} {sum(v > 0 for v in k.values()):3d} {bp[len(bp) // 2] if bp else 0:+6.2f} {1e4 * sum(A[g].values()) / max(tn, 1):+6.2f} ${tn:,.0f}")
