"""Does the long-lived fleet pull quotes when our rules would? Read-only tape study.  python3 pullprobe.py <tape> <T0 sim s> fleet=<uids> x2=212 x4=58
(A) order ids vs time (our queue records) -> fleet order age at fill; (B) share of each group's maker fills in a state where OUR flow_pull (near-touch new-order
imbalance over 10 s > 0.3, pulled 3 s) or OUR thin rule (own-side top size < 0.77 x other side) would have removed that side; edge / kept per state."""
import json, sys, collections, bisect, statistics as stt
tape, T0 = sys.argv[1], float(sys.argv[2])
G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[3:]}
who = {u: g for g, us in G.items() for u in us}
OF = collections.defaultdict(dict); SN = collections.defaultdict(dict); FILLS = []; QID = {}
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 90000 or t < T0: continue
    r = json.loads(l); b = r.get("book")
    if b is None or b >= 102: continue
    if "Mi" in r:
        if r["Ma"] in who and r["Ma"] != r["Ta"]: FILLS.append((t, b, r["p"], r["q"], r["s"], who[r["Ma"]], r["Mi"]))
    elif "of" in r:
        OF[b][int(t)] = (r["of"]["nb2"], r["of"]["na2"])
    elif "bids" in r:
        if r["bids"] and r["asks"]: SN[b][int(t)] = (r["bid"], r["ask"], r["bids"][0][1], r["asks"][0][1])
    elif "queue" in r:
        for q in r["queue"]:
            QID.setdefault((b, q[4]), t)
# (A) id -> time map from our own orders
PB = collections.defaultdict(list)
for (bb, k), v in QID.items(): PB[bb].append((k, v))
inv = n_ = 0
for bb in PB:
    PB[bb].sort(); tt = [v for k, v in PB[bb]]; inv += sum(1 for a, b2 in zip(tt, tt[1:]) if b2 < a - 5); n_ += len(tt) - 1
print(f"(A) per book: {inv} inversions > 5 s of {n_} steps")
def placed(mi, b):
    ids = [k for k, v in PB[b]]; ts_ = [v for k, v in PB[b]]
    j = bisect.bisect_left(ids, mi)
    if j == 0 or j >= len(ids): return None
    return ts_[j - 1] + (ts_[j] - ts_[j - 1]) * (mi - ids[j - 1]) / max(1, ids[j] - ids[j - 1])
def near(b, s):
    nb = na = 0.0
    for k in range(s - 9, s + 1):
        x = OF[b].get(k)
        if x: nb += x[0]; na += x[1]
    return (nb - na) / (nb + na) if nb + na > 0 else 0.0
rows = []
for t, b, p, q, s, g, mi in FILLS:
    sec = int(t); sn = SN[b].get(sec - 1) or SN[b].get(sec - 2)
    later = SN[b].get(sec + 20)
    if not sn or not later: continue
    mid = (sn[0] + sn[1]) / 2; mid2 = (later[0] + later[1]) / 2
    buy = (s == 1)                                   # side 1 = maker bought (vfill.py convention)
    pulled_flow = any((near(b, k) < -0.3) if buy else (near(b, k) > 0.3) for k in range(sec - 3, sec))
    own, oth = (sn[2], sn[3]) if buy else (sn[3], sn[2])
    thin = own < 0.77 * oth
    sg = 1 if buy else -1
    edge = sg * (mid - p) / mid * 1e4; kept = sg * (mid2 - p) / mid * 1e4
    pt = placed(mi, b); age = (t - pt) if pt is not None else None
    rows.append((g, "$300" if b < 63 else "calm", pulled_flow, thin, edge, kept, p * q, age))
def summ(v):
    if not v: return "   -"
    d = sum(x[6] for x in v)
    return f"n {len(v):5d} edge {sum(x[4] * x[6] for x in v) / d:+5.2f} kept {sum(x[5] * x[6] for x in v) / d:+5.2f}"
for grp in ("$300", "calm"):
    print(f"\n== {grp} books (dollar-weighted bp; kept = mid 20 s later vs fill)")
    for g in G:
        v = [x for x in rows if x[0] == g and x[1] == grp]
        if not v: continue
        D = sum(x[6] for x in v)
        fp = [x for x in v if x[2]]; th = [x for x in v if x[3]]
        ages = sorted(x[7] for x in v if x[7] is not None and x[7] >= 0)
        a = (f"age median {stt.median(ages):6.1f} s | >10 s {sum(1 for y in ages if y > 10) / len(ages):.0%} | >60 s {sum(1 for y in ages if y > 60) / len(ages):.0%} | "
             f">300 s {sum(1 for y in ages if y > 300) / len(ages):.0%}") if ages else "age n/a"
        print(f"{g:6s} fills {len(v):5d} | ALL {summ(v)}\n       flow-pull state {sum(x[6] for x in fp) / D:5.1%} of $  {summ(fp)} | rest {summ([x for x in v if not x[2]])}"
              f"\n       thin-queue state {sum(x[6] for x in th) / D:5.1%} of $  {summ(th)} | rest {summ([x for x in v if not x[3]])}\n       {a}")
