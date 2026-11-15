"""Per taker id on $300 books: trades, $ share, median $ per taker-second (same book/sec/taker/side summed), share of $10k+ events, and the 60-s mid move after its
trades in its direction (persistence of its flow), plus how often the SAME taker id trades the same side again on the same book within 60 s."""
import json, sys, collections, statistics as st
tape, LO, HI = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
B = collections.defaultdict(dict); EV = collections.defaultdict(float); seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0 or b'"book": ' not in l: continue
    try: ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    except ValueError: continue
    if s < LO or s > HI + 65: continue
    j = l.find(b'"book": '); bk = int(l[j + 8:l.index(b",", j)])
    if bk >= 128: continue
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask"): B[bk][s] = (r["bid"] + r["ask"]) / 2
    elif b'"Ta"' in l and s < HI:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen: continue
        seen.add(k); EV[(bk, s, r.get("Ta"), r["s"])] += r["p"] * r["q"]
by = collections.defaultdict(list); tot = 0.0
for (bk, s, ta, side), v in EV.items():
    m0 = B[bk].get(s - 1); m1 = B[bk].get(s + 60); sg = 1 if side == 0 else -1
    mv = sg * (m1 - m0) / m0 * 1e4 if (m0 and m1) else None
    by["miner" if ta is not None and ta >= 0 else str(ta)].append((v, mv, bk, s, side)); tot += v
rows = []
for t, v in by.items():
    usd = sum(x[0] for x in v); big = sum(x[0] for x in v if x[0] >= 10000)
    mvs = [(x[0], x[1]) for x in v if x[1] is not None]; w = sum(a for a, _ in mvs)
    rep = collections.defaultdict(list)
    for x in v: rep[(x[2], x[4])].append(x[3])
    again = sum(1 for k, ts_ in rep.items() for a, b in zip(sorted(ts_), sorted(ts_)[1:]) if b - a <= 60); n = len(v)
    rows.append((usd, f"  taker {t:>6}: events {n:6d} | {usd / tot:4.0%} of $ | median ${st.median(x[0] for x in v):7,.0f} | $10k+ events {big / usd:4.0%} of its $ | 60-s move its way {sum(a * b for a, b in mvs) / w if w else 0:+.2f} bp | same side again ≤ 60 s {again / n:4.0%}"))
for _, r in sorted(rows, reverse=True)[:14]: print(r)
