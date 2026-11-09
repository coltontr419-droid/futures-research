"""§1350: how much head-start volume is still inside the validator's 3-sim-h making window, and the projected volume (→ making credit at constant
quality) as the window moves on. From the pace ledger [book, start, notional, id, ts_ns].  python3 windowproj.py <ledger> <now sim s> <credit now> <sim s per wall h>"""
import json, sys, collections
led, NOW, CRED, RATE_H = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]); W = 10800.0
F = []
for l in open(led):
    r = json.loads(l); F.append((r[4] / 1e9, r[0], r[2]))
F = [f for f in F if f[0] <= NOW]
grp = lambda b: "$300" if b < 63 else "calm" if b < 102 else "4-dec"
recent = [f for f in F if f[0] > NOW - 1800]                     # steady rate from the last 0.5 sim h
rate = collections.Counter(); [rate.update({grp(b): v / 1800}) for t, b, v in recent]
inwin = lambda T: collections.Counter({g: sum(v for t, b, v in F if T - W < t <= NOW and grp(b) == g) for g in ("$300", "calm", "4-dec")})
now_v = inwin(NOW); tot_now = sum(now_v.values())
print(f"window now (sim {NOW - W:.0f}–{NOW:.0f}): $300 ${now_v['$300']:,.0f} | calm ${now_v['calm']:,.0f} | 4-dec ${now_v['4-dec']:,.0f} | total ${tot_now:,.0f}")
print(f"steady rate (last 0.5 sim h) per sim h: $300 ${rate['$300'] * 3600:,.0f} | calm ${rate['calm'] * 3600:,.0f} | 4-dec ${rate['4-dec'] * 3600:,.0f} → full steady window ${sum(rate.values()) * W:,.0f}")
print("wall +h  sim end   window $ (past part + steady part)   → credit at constant quality")
for h in (0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15):
    T = NOW + h * RATE_H
    past = sum(inwin(T).values()); fut = sum(rate.values()) * min(W, T - NOW)
    v = past + fut
    print(f"  +{h:2d} h   {T:7.0f}  ${v:12,.0f}  (${past:,.0f} + ${fut:,.0f})      → {CRED * v / tot_now:5.0f}")
