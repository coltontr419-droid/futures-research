"""MVTRX skill as the VALIDATOR computes it (§1211 add. 20): per book, alpha = Σ inventory × Δmid over the book's prints (pre-print
inventory, mark_mode "mid") − mean inventory over prints × drift (Σ Δmid); notional = Σ fill price × q of our fills (maker and taker);
hurdle_filter at 2.3 bp of that notional; kappa_floored (floor 0, min books 4) over the kept books. Last LAST sim minutes of the tape; the
starting inventory is unknown, so the window is scored from inventory 0 (exact when the window starts flat; on held books an offset).
    python skill_val.py <tape> <uid> <last sim min> [skip_file]"""
import json, sys
from collections import defaultdict
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_floored, hurdle_filter
tape, me, last = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
skip = set(map(int, open(sys.argv[4]).read().split())) if len(sys.argv) > 4 and not sys.argv[4].startswith("--") else set()
ev, seen, tmax = defaultdict(list), set(), 0
for line in open(tape):
    r = json.loads(line)
    if r.get("ts", 0) >= 60000 * 10 ** 9: continue      # §1283: current simulation only — x3's tape still starts with pre-reset lines (ts ≈ 77,000-86,400 s), which
                                                    # made "the last N sim min" the OLD sim and, for re-registered slots, the slot's previous owner
    if "p" in r:
        k = (r["book"], r.get("id"), r["ts"])
        if k in seen: continue
        seen.add(k); ev[r["book"]].append((r["ts"], 1, r)); tmax = max(tmax, r["ts"])
    elif r.get("bid") and r.get("ask"):
        ev[r["book"]].append((r["ts"], 0, (r["bid"] + r["ask"]) / 2))
t0 = tmax - last * 6e10
alpha, notional = {}, {}
for b, es in ev.items():
    es.sort(key=lambda e: (e[0], e[1])); mid = None; inv = 0.0; mtm = isum = drift = 0.0; n = 0; notl = 0.0; prev = None
    for ts, kind, x in es:
        if ts < t0: 
            if kind == 0: mid = x
            continue
        if kind == 0: mid = x; continue
        r = x; p = mid if mid is not None else r["p"]
        if prev is not None and p != prev:
            mtm += inv * (p - prev); drift += p - prev
        d = 0.0
        if r.get("Ma") == me: d += r["q"] if r["s"] == 1 else -r["q"]
        if r.get("Ta") == me: d += r["q"] if r["s"] == 0 else -r["q"]
        if d: notl += abs(d) * r["p"]
        inv += d; isum += inv; n += 1; prev = p
    if notl > 0 and n:
        alpha[b] = mtm - isum / n * drift; notional[b] = notl
kept = hurdle_filter({me: alpha}, {me: notional}, 2.3)[me]
def show(name, bs):
    a = {b: alpha[b] for b in bs if b in alpha}; k = {b: kept[b] for b in bs if b in kept}
    bp = sorted(1e4 * alpha[b] / notional[b] for b in a)
    print(f"{name:8} books {len(a):3d} | kept by hurdle {len(k):3d} (pos {sum(v > 0 for v in k.values())}, neg {sum(v < 0 for v in k.values())}) | "
          f"Σα {sum(a.values()):9.1f} | α/notional bp median {bp[len(bp)//2] if bp else 0:+.2f} | kappa(kept) {kappa_floored(list(k.values()), 0.0, 4):+.3f}")
show("calm", [b for b in alpha if b not in skip]); show("skipped", [b for b in alpha if b in skip]); show("all", list(alpha))
if "--worst" in sys.argv:
    W = sorted(alpha, key=lambda b: alpha[b])[:10]
    print("worst books: book | α $ | α bp of notional | notional $ | inventory at end ($) | book move over the window (bp)")
    for b in W:
        es = sorted(ev[b], key=lambda e: (e[0], e[1])); mids = [x for ts, k, x in es if k == 0 and ts >= t0]
        inv = 0.0; last_p = None
        for ts, kind, x in es:
            if kind == 1 and ts >= t0:
                r = x; last_p = r["p"]
                if r.get("Ta") == me: inv += r["q"] if r["s"] == 0 else -r["q"]
                if r.get("Ma") == me: inv += r["q"] if r["s"] == 1 else -r["q"]
        mv = (mids[-1] - mids[0]) / mids[0] * 1e4 if len(mids) > 1 else 0
        print(f"  {b:3d} | {alpha[b]:+8.1f} | {1e4 * alpha[b] / notional[b]:+7.1f} | {notional[b]:9,.0f} | {inv * (last_p or 0):+9,.0f} | {mv:+7.1f}")
    print("share of all negative α from the worst 5 books:", round(sum(alpha[b] for b in W[:5]) / sum(a for a in alpha.values() if a < 0), 2))
