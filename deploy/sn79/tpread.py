"""x1 exit test read: rebuild positions per book since T 79,473 by group (book mod 4). Round trips closed and open, mid-to-mid; scorer α and hurdle per group."""
import bisect, json, collections, statistics as st, sys
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_floored, hurdle_filter
T0 = 79473; U = 22
ev = collections.defaultdict(list); seen = set()
fh = open("/opt/mvtrx/live_tape_x1.jsonl", "rb"); fh.seek(0, 2); fh.seek(max(0, fh.tell() - 280_000_000)); fh.readline()
for l in fh:
    if b'"bid"' in l[:60]:
        i = l.find(b'"bids"'); r = json.loads(l[:i].rstrip(b', ') + b"}")
        if r.get("bid") and r.get("ask") and r["ts"] / 1e9 >= T0 - 30: ev[r["book"]].append((r["ts"], 0, (r["bid"] + r["ask"]) / 2))
    elif b'"p"' in l:
        r = json.loads(l); k = (r["book"], r.get("id"), r["ts"])
        if r["ts"] / 1e9 >= T0 and k not in seen:
            seen.add(k); ev[r["book"]].append((r["ts"], 1, r))
G = ("A clock", "B +4 bp 1h", "C +8 bp 1h", "D +8 bp no stop"); A = collections.defaultdict(dict); N = collections.defaultdict(dict); RT = collections.defaultdict(list); OP = collections.defaultdict(list); end = 0
for b, es in ev.items():
    es.sort(key=lambda e: (e[0], e[1])); g = b % 4; mid = None; inv = 0.0; mtm = isum = drift = 0.0; n = 0; notl = 0.0; prev = None; cur = None
    for ts, kind, x in es:
        if kind == 0: mid = x; end = max(end, ts); continue
        p = mid if mid is not None else x["p"]
        if prev is not None and p != prev: mtm += inv * (p - prev); drift += p - prev
        d = 0.0
        if x.get("Ma") == U: d += x["q"] if x["s"] == 1 else -x["q"]
        if x.get("Ta") == U: d += x["q"] if x["s"] == 0 else -x["q"]
        if d:
            notl += abs(d) * x["p"]
            if abs(inv) * p < 1: cur = (ts, p, 1 if d > 0 else -1); inv = 0.0
        new = inv + d
        if d and cur and abs(new) * p < 1:
            RT[g].append(((ts - cur[0]) / 1e9, cur[2] * (p - cur[1]) / cur[1] * 1e4)); cur = None
        inv = new; isum += inv; n += 1; prev = p
    if notl > 0 and n:
        A[g][b] = mtm - isum / n * drift; N[g][b] = notl
        if cur: OP[g].append(((end - cur[0]) / 1e9, cur[2] * ((mid or cur[1]) - cur[1]) / cur[1] * 1e4))
print("sim min elapsed", round((end / 1e9 - T0) / 60, 1))
print("group | closed n, mean bp, win, hold s | open n, mark bp, age s | all positions mean bp | books traded, kept, kept pos, median α bp, total α bp, $ notional")
for g in range(4):
    C = RT[g]; O = OP[g]; c = lambda v: max(-50, min(50, v)); all_ = [c(x[1]) for x in C] + [c(x[1]) for x in O]
    k = hurdle_filter({0: A[g]}, {0: N[g]}, 2.3)[0]; bp = sorted(1e4 * A[g][b] / N[g][b] for b in A[g]); tn = sum(N[g].values())
    print(f"{G[g]:16} | {len(C):3d} {st.mean(c(x[1]) for x in C) if C else 0:+6.2f} {sum(x[1] > 0 for x in C) / max(len(C), 1):4.0%} {st.median(x[0] for x in C) if C else 0:5.0f} | {len(O):3d} {st.mean(c(x[1]) for x in O) if O else 0:+6.2f} {st.median(x[0] for x in O) if O else 0:5.0f} | {st.mean(all_) if all_ else 0:+6.2f} | {len(A[g]):3d} {len(k):3d} {sum(v > 0 for v in k.values()):3d} {bp[len(bp) // 2] if bp else 0:+6.2f} {1e4 * sum(A[g].values()) / max(tn, 1):+6.2f} ${tn:,.0f}")
