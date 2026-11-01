"""The making pool's actual quality factor (decisions.md §1209), reproduced from a tape: per maker fill, captured c = (mid at fill − p)·q
signed for the maker, realized r = (mid 20 s later − p)·q signed the same way and capped to ±|c|; quality R/C = Σr / Σc over fills
(clamped to [0, 1] by the validator; shown unclamped here). The validator marks against prints, here the mid — an approximation.
Also two-sided capture per book (Σ_b 2·min(buy_b, sell_b)), the credit the quality multiplies. Per arm when n arms > 1.

    python rc_quality.py <tape.jsonl> <our uid> [n arms]
"""
import bisect
import json
import sys
from collections import defaultdict

tape, me = sys.argv[1], int(sys.argv[2]); n = int(sys.argv[3]) if len(sys.argv) > 3 else 1
H = 20.0
mids, fills = defaultdict(list), []
for line in open(tape):
    r = json.loads(line)
    if "p" in r and r.get("Ma") is not None and r["Ma"] >= 0:
        fills.append(r)
    elif r.get("bid") and r.get("ask"):
        mids[r["book"]].append((r["ts"] / 1e9, (r["bid"] + r["ask"]) / 2))
acc = defaultdict(lambda: {"C": 0.0, "R": 0.0, "n": 0, "buy": defaultdict(float), "sell": defaultdict(float)})
for t in fills:
    ml = mids[t["book"]]; ts = t["ts"] / 1e9
    j = bisect.bisect_right(ml, (ts, float("inf"))) - 1; k = bisect.bisect_left(ml, (ts + H,))
    if j < 0 or k >= len(ml):
        continue
    maker_buy = t["s"] == 1                                 # taker sold → the maker bought
    sgn = 1 if maker_buy else -1
    c = sgn * (ml[j][1] - t["p"]) * t["q"]
    r = sgn * (ml[k][1] - t["p"]) * t["q"]
    r = max(-abs(c), min(abs(c), r))
    key = ("ours", t["book"] % n) if t["Ma"] == me else ("field", t["Ma"])
    a = acc[key]; a["C"] += c; a["R"] += r; a["n"] += 1
    (a["buy"] if maker_buy else a["sell"])[t["book"]] += c
def two_sided(a):
    return max(0.0, sum(2 * min(a["buy"].get(b, 0.0), a["sell"].get(b, 0.0)) for b in set(a["buy"]) | set(a["sell"])))
ours = sorted(k for k in acc if k[0] == "ours")
for k in ours:
    a = acc[k]
    print(f"ours{'' if n == 1 else f' arm {k[1]}'}: fills {a['n']:5d} | captured C {a['C']:10.1f} | realized R {a['R']:10.1f} | "
          f"quality R/C {a['R'] / a['C'] if a['C'] > 0 else float('nan'):+.3f} | two-sided capture {two_sided(a):10.1f}")
field = [acc[k] for k in acc if k[0] == "field" and acc[k]["n"] >= 30]
q = sorted(a["R"] / a["C"] for a in field if a["C"] > 0)
if q:
    print(f"field ({len(q)} makers with ≥ 30 fills): quality R/C median {q[len(q) // 2]:+.3f}, p25 {q[len(q) // 4]:+.3f}, p75 {q[3 * len(q) // 4]:+.3f}")

credits = sorted((two_sided(a) * max(0.0, min(1.0, a["R"] / a["C"])) if a["C"] > 0 else 0.0) for a in field)
caps = sorted(two_sided(a) for a in field)
if credits:
    tot = sum(credits)
    print(f"field two-sided capture median {caps[len(caps) // 2]:.1f}, p90 {caps[int(len(caps) * .9)]:.1f} | credit (capture × clamp R/C) median "
          f"{credits[len(credits) // 2]:.1f}, p90 {credits[int(len(credits) * .9)]:.1f}, total {tot:.0f}")
    for k in ours:
        a = acc[k]; cr = two_sided(a) * max(0.0, min(1.0, a["R"] / a["C"])) if a["C"] > 0 else 0.0
        rank = sum(1 for x in credits if x > cr) + 1
        print(f"ours{'' if n == 1 else f' arm {k[1]}'}: credit {cr:.1f} → rank {rank} of {len(credits) + 1}, share of this tape's making credit {cr / (tot + cr):.2%}")
