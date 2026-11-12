"""Attack the volume pacing (decisions.md §1255) through the REAL agent methods. Hard cap 500,000 per book per 86,400 sim s (10 × $50k wealth).
A maker that is filled the instant it may quote is the worst case. Every test prints PASS or FAIL.  python test_pace.py <agent.py> [old agent.py]"""
import importlib.util, json, os, random, sys, tempfile, argparse, collections
sys.path.insert(0, "/opt/mvtrx/repo")
CAP, DAY = 500000.0, 86400

def agent(path, **kw):
    spec = importlib.util.spec_from_file_location("QAT" + str(abs(hash((path, str(sorted(kw.items())))))), path); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    cfg = argparse.Namespace(size=0.06, skew=10.0, max_inv=0.3, edge=1, model="/opt/mvtrx/agents/model30_of.json", alpha_k=1.0, join=1, pull=1.0, max_units=40, lazy_load=1, lean=1, raw=1,
                             cancel_first=1, flow_pull=0.3, flow_win=10, flow_cool=3, data_dir=tempfile.mkdtemp(), **kw)
    return mod.QuoteAgent(93, cfg, tempfile.mkdtemp())

def fill(a, b, t, v, new):
    a._pace[b].append((t, v))
    if new: a._tok_spend(b, t, v)

def attack(a, new, days=3, seed=1, order=3000.0, sides=2, step=1):
    """Fill every order set whenever the gate is open, on one book. Returns (worst rolling 24h $, $ in the last full day, longest idle s, fills)."""
    rng = random.Random(seed); b = 70; fills = collections.deque(); roll = worst = 0.0; last = idle = 0; n = 0; day3 = 0.0
    for t in range(0, days * DAY, step):
        a._sec = t
        if a._paced_out(b):
            continue
        idle = max(idle, t - last); last = t
        for _ in range(rng.randint(1, sides)):
            v = order * rng.uniform(.3, 1.0); fill(a, b, t, v, new); fills.append((t, v)); roll += v; n += 1
            if t >= (days - 1) * DAY: day3 += v
        while fills and fills[0][0] <= t - DAY:
            roll -= fills.popleft()[1]
        worst = max(worst, roll)
    return worst, day3, idle, n

new_path = sys.argv[1]; old_path = sys.argv[2] if len(sys.argv) > 2 else None; bad = 0
def check(name, ok, detail):
    global bad
    print(("PASS " if ok else "FAIL ") + name + " | " + detail); bad += 0 if ok else 1

for name, kw in (("typical $3k orders", {}), ("large $10k orders", {"order": 10000.0}), ("two sides each step", {"sides": 2, "order": 3000.0}), ("one huge $50k sweep each time", {"order": 50000.0, "sides": 1})):
    a = agent(new_path, pace_cap=450000); w, d3, idle, n = attack(a, True, **kw)
    check(f"bucket, {name}", w < CAP, f"worst 24h ${w:,.0f} of hard ${CAP:,.0f} | last day ${d3:,.0f} | longest idle {idle} sim s | {n} fills")

a = agent(new_path, pace_cap=450000); w, d3, idle, n = attack(a, True)
check("no stop-go: idle stays short", idle < 1800, f"longest idle {idle} sim s (old window: hours)")
check("budget is usable, not starved", d3 > 400000, f"traded ${d3:,.0f} in a day of the $450,000 budget")
if old_path:
    o = agent(old_path, pace_cap=450000, pace_win=5400); w2, d2, idle2, n2 = attack(o, False)
    print(f"INFO old 90-min window, same attack: worst 24h ${w2:,.0f}, longest idle {idle2} sim s ({idle2 / 3600:.1f} sim h ≈ {idle2 / 3600 * 5:.0f} wall h)")

L = os.path.join(tempfile.mkdtemp(), "pace_UIDN.ledger"); path = L.replace("UIDN", "93")
a = agent(new_path, pace_cap=450000, pace_ledger=L); a._sec = 0; rows = []
for t in range(0, 5000, 7):
    a._sec = t; fill(a, 70, t, 1500.0, True); rows.append([70, t, 1500.0, t, t])
open(path, "w").write("".join(json.dumps(r) + "\n" for r in rows))
b = agent(new_path, pace_cap=450000, pace_ledger=L); b._sec = a._sec
x, y = a._tok_accrue(70, a._sec)[0], b._tok_accrue(70, b._sec)[0]
check("restart resumes the same balance", abs(x - y) < 1e-6, f"before ${x:,.0f} after ${y:,.0f}")
check("restart cannot reopen a spent book", b._paced_out(70), "book stays blocked after restart")

a = agent(new_path, pace_cap=450000); a._sec = 86000
for t in range(86000, 86400, 2):
    a._sec = t; fill(a, 70, t, 1500.0, True)
a._sec = 86399; before = a._tok_accrue(70, 86399)[0]; a._sec = 5; bal = a._tok_accrue(70, 5)[0]
check("sim clock reset gives no free budget", bal <= before + 1e-6, f"balance ${before:,.0f} → ${bal:,.0f}")

a = agent(new_path, pace_cap=450000); a._sec = 0
check("fresh UID can quote at once", not a._paced_out(70), "full burst available")
a = agent(new_path, pace_cap=450000); a._sec = 0
for k in range(400):
    a._sec = k; fill(a, 70, k, 20000.0, True)
a._sec = 400
check("24h backstop holds on its own", a._pace_day(70) >= 450000 and a._paced_out(70), f"day ${a._pace_day(70):,.0f}")
a2 = agent(new_path, pace_cap=450000, pace_k=5, pace_win=86400); a2._sec = 0
check("pace_k / pace_win cannot loosen it", a2.pace_rate == 450000 / DAY, f"rate ${a2.pace_rate:.3f}/s regardless")
d = tempfile.mkdtemp(); L = os.path.join(d, "pace_UIDN.ledger"); open(os.path.join(d, "pace_93.ledger"), "w").close()
a = agent(new_path, pace_cap=450000, pace_ledger=L); a._sec = 100
json.dump({"70": 300000.0, "71": 500.0}, open(os.path.join(d, "pace_sync_93.json"), "w"))
a._pace_sync(); first = a._pace_day(70); a._sec = 110; a._pace_sync()
check("validator figure above the ledger is charged", first == 300000.0 and a._paced_out(70), f"book 70 day ${first:,.0f}, blocked")
check("charged once, not every sim minute", a._pace_day(70) == 300000.0, f"after a second sync ${a._pace_day(70):,.0f}")
check("small lag is ignored", a._pace_day(71) == 0.0, "book 71 uncharged")
b = agent(new_path, pace_cap=450000, pace_ledger=L); b._sec = 110
check("a charge survives a restart", b._pace_day(70) == 300000.0, f"book 70 day ${b._pace_day(70):,.0f}")
d = tempfile.mkdtemp(); L = os.path.join(d, "pace_UIDN.ledger"); rows = [[70, t, 5000.0, t, t] for t in range(80000, 86400, 200)] + [[70, t, 5000.0, 10 ** 6 + t, t] for t in range(0, 3000, 200)]
open(os.path.join(d, "pace_93.ledger"), "w").write("".join(json.dumps(r) + "\n" for r in rows))
a = agent(new_path, pace_cap=450000, pace_ledger=L); a._sec = 3000
class E: pass
a._pace_shift_done = False; a._sec = 3000
newest = max(h[-1][0] for h in a._pace.values() if h)
for bk in a._pace:
    if newest > a._sec + 60:
        dd = a._sec - newest; a._pace[bk] = [(t + dd, v) for t, v in a._pace[bk]]
        for st in a._tok.values(): st[1] += dd
want = 5000.0 * len(rows)
check("restart after a sim reset keeps all the volume", abs(a._pace_day(70) - want) < 1, f"counted ${a._pace_day(70):,.0f} of ${want:,.0f}")
a = agent(new_path, pace_cap=450000, rev_tp_bp=4.0); a._rev_px[5] = 100.0
check("target: long closes at +4 bp", a._rev_take(5, 10.0, 100.04) and not a._rev_take(5, 10.0, 100.03), "100.04 yes, 100.03 no")
check("target: short closes at +4 bp", a._rev_take(5, -10.0, 99.96) and not a._rev_take(5, -10.0, 99.97), "99.96 yes, 99.97 no")
check("target: flat position does nothing", not a._rev_take(5, 0.0, 200.0), "tgt 0")
o = agent(new_path, pace_cap=450000); o._rev_px[5] = 100.0
check("target off: never fires", not o._rev_take(5, 10.0, 200.0), "rev_tp_bp 0")
a = agent(new_path, pace_cap=450000); a._sec = 86300; a._clock_check(); a._rev = {5: (3.0, 86000)}; a._last_take = {5: 86290}; a._pull_until = {5: {0: 86303}}; a._ioc_logged = 86250; a._mids = {5: {86299: 1.0}}
a._sec = 20; a._clock_check(); d = 20 - 86300
check("clock reset shifts a position's entry time", a._rev[5] == (3.0, 86000 + d) and a._sec - a._rev[5][1] == 300, f"age after reset {a._sec - a._rev[5][1]} s (was 300)")
check("clock reset shifts take / pull / log stamps", a._last_take[5] == 86290 + d and a._pull_until[5][0] == 86303 + d and a._ioc_logged == 86250 + d, "shifted")
check("clock reset clears per-second history", a._mids == {}, "cleared")
a._sec = 25; a._clock_check(); check("normal steps do nothing", a._rev[5] == (3.0, 86000 + d), "unchanged")
class RF:
    def __init__(self, p): self.p = p
    def predict(self, b, t): return self.p
a = agent(new_path, pace_cap=450000, rev_legs=4, rev_leg_bp=6.0, rev_leg_dir=-1, rev_tp_bp=8.0); a._rf = RF(5.0); a._sec = 10
a._rev_px[7] = 100.0; a._rev_n[7] = 1; a._rev_last[7] = 100.0; t1 = 10.0
check("losers: no add before the move", a._rev_leg(7, t1, 99.95) == t1, "−5 bp")
t2 = a._rev_leg(7, t1, 99.94); check("losers: add at −6 bp", abs(t2 - (t1 + 1000 / 99.94)) < 1e-9 and a._rev_n[7] == 2, f"target {t2:.2f}")
check("losers: average price follows", abs(a._rev_px[7] - (100.0 + 99.94) / 2) < 1e-9, f"avg {a._rev_px[7]:.3f}")
check("losers: target measured from the average", a._rev_take(7, t2, (100.0 + 99.94) / 2 * 1.00081) and not a._rev_take(7, t2, 100.04), "+8 bp from avg")
a._rf = RF(-5.0); check("losers: no add when the model has turned", a._rev_leg(7, t2, 99.88) == t2, "model against")
a._rf = RF(5.0); x = t2
for p in (99.88, 99.82, 99.76, 99.70): x = a._rev_leg(7, x, p)
check("losers: never more than 4 legs", a._rev_n[7] == 4 and abs(x - (t1 + 1000 / 99.94 + 1000 / 99.88 + 1000 / 99.82)) < 1e-6, f"legs {a._rev_n[7]}")
w = agent(new_path, pace_cap=450000, rev_legs=3, rev_leg_bp=4.0, rev_leg_dir=1, rev_tp_bp=8.0); w._rf = RF(-5.0); w._sec = 10; w._rev_px[9] = 100.0; w._rev_n[9] = 1; w._rev_last[9] = 100.0
check("winners: short adds on a favourable drop", w._rev_leg(9, -10.0, 99.95) < -10.0 and w._rev_n[9] == 2, "−4 bp for a short")
check("winners: no add on an adverse move", w._rev_leg(9, -10.0 - 1000 / 99.95, 100.10) == -10.0 - 1000 / 99.95, "adverse")
o = agent(new_path, pace_cap=450000); o._rf = RF(5.0); o._sec = 10; o._rev_px[7] = 100.0; o._rev_n[7] = 1; o._rev_last[7] = 100.0
check("legs off: never adds", o._rev_leg(7, 10.0, 90.0) == 10.0, "rev_legs 1")
for kw in ({}, {"order": 10000.0}, {"order": 50000.0, "sides": 1}):
    a = agent(new_path, pace_cap=450000, pace_steady=350000, pace_start=100000); w, d3, idle, n = attack(a, True, **kw)
    check(f"front-loaded start (steady 350k + start 100k, backstop 450k), {kw or 'typical'}", w < CAP, f"worst 24h ${w:,.0f} of ${CAP:,.0f} | last day ${d3:,.0f} | {n} fills")
a = agent(new_path, pace_cap=380000, pace_start=100000); w, d3, idle, n = attack(a, True, days=1)
a2 = agent(new_path, pace_cap=450000); w2, d32, idle2, n2 = attack(a2, True, days=1, seed=1)
b = agent(new_path, pace_cap=450000, pace_steady=350000, pace_start=100000); b._sec = 0; spent = 0.0; t = 0
while not b._paced_out(70) and t < 3600: b._sec = t; fill(b, 70, t, 3000.0, True); spent += 3000.0; t += 1
c_ = agent(new_path, pace_cap=450000); c_._sec = 0; spent2 = 0.0; t = 0
while not c_._paced_out(70) and t < 3600: c_._sec = t; fill(c_, 70, t, 3000.0, True); spent2 += 3000.0; t += 1
check("front-loaded start lets a fresh book trade more at once", spent > 10 * spent2, f"before the first block: ${spent:,.0f} vs ${spent2:,.0f} with the normal start")
check("start is not refilled", b._tok_accrue(70, 10 ** 6)[0] <= 350000 / 86400 * 900 + 1, f"balance after a long wait ${b._tok_accrue(70, 10 ** 6)[0]:,.0f} (normal burst cap)")
d = tempfile.mkdtemp(); L = os.path.join(d, "pace_UIDN.ledger"); open(os.path.join(d, "pace_93.ledger"), "w").write(json.dumps([70, 100, 50000.0, 1, 1]) + "\n")
r = agent(new_path, pace_cap=450000, pace_steady=350000, pace_start=100000, pace_ledger=L); r._sec = 200
a = agent(new_path, pace_cap=450000, pace_steady=350000, pace_start=100000); w, d1, idle, n = attack(a, True, days=1)
check("front-loaded: first day's total is not cut", d1 > 400000, f"first 24 h traded ${d1:,.0f} (normal start: ≈ $450k)")
check("a restart does not re-grant the start to a book with history", r._tok_accrue(70, 200)[0] < 100000 - 40000, f"balance ${r._tok_accrue(70, 200)[0]:,.0f}")

# §1273 copy mode
class RFt:
    def __init__(self, p): self.p = p; self.th = 1.0
    def predict(self, b, t): return self.p
k = agent(new_path, pace_cap=450000, rev_copy=1, rev_usd=1500, rev_max_usd=15000, rev_tp_bp=6.0, rev_slice=0.1, rev_slice_cool=120, sleeve_step=900); k._rf = RFt(5.0); k._sec = 0
t_, a_ = k._rev_copy_step(3, 0.0, -10 ** 9, 100.0, 5.0); check("copy: a signal on a flat book opens REV_USD", abs(t_ * 100 - 1500) < 1e-6 and k._rev_px[3] == 100.0, f"${t_ * 100:,.0f}")
k._sec = 900; t2_, a_ = k._rev_copy_step(3, t_, a_, 99.0, 5.0); check("copy: an agreeing signal adds, average follows", abs(t2_ - (15 + 1500 / 99)) < 1e-9 and abs(k._rev_px[3] - (100 * 15 + 99 * 1500 / 99) / (15 + 1500 / 99)) < 1e-9, f"avg {k._rev_px[3]:.3f}")
k._rf = RFt(-5.0); t3_, a3_ = k._rev_copy_step(3, t2_, a_, 99.0, -5.0); check("copy: an opposite signal is ignored (no stop)", t3_ == t2_, "held")
x_ = t2_; k._rf = RFt(5.0)
for i in range(30): k._sec = 2000 + 900 * i; x_, a_ = k._rev_copy_step(3, x_, a_, 99.5, 5.0)
check("copy: never above REV_MAX_USD", x_ * 99.5 <= 15000 + 1e-6, f"${x_ * 99.5:,.0f}")
m0 = k._rev_px[3]; up = m0 * 1.0007; k._sec = 40000; y_, _ = k._rev_copy_step(3, x_, a_, up, None); check("copy: slice 10% at +7 bp", abs(y_ - 0.9 * x_) < 1e-9 and k._rev_px[3] == m0, "average unchanged")
k._sec = 40060; z_, _ = k._rev_copy_step(3, y_, a_, up, None); check("copy: slices wait REV_SLICE_COOL", z_ == y_, "60 s later: no slice")
k._sec = 40000 + 121 * 40
for i in range(60): k._sec += 121; z_, _ = k._rev_copy_step(3, z_, a_, up, None)
check("copy: slices run down to flat", z_ == 0.0 and 3 not in k._rev_px, "flat")
k._sec = 50000; w_, _ = k._rev_copy_step(3, 10.0, a_, m0 * 1.0005, None) if k._rev_px.setdefault(3, m0) else None; check("copy: no slice under the target", w_ == 10.0, "+5 bp")
def copy_attack(seed, days=3, step=5, sstep=60, swing=12.0, trend=0.0):
    """Full path on one book: signals every check, price swinging ±SWING bp so slices fire constantly, IOC clips of $700 filled instantly,
    the agent's own pace gate on new exposure only; exits always go. Returns worst rolling 24h $."""
    a = agent(new_path, pace_cap=450000, rev_copy=1, rev_usd=1500, rev_max_usd=15000, rev_tp_bp=6.0, rev_slice=0.1, rev_slice_cool=120, sleeve_step=sstep, rev_clip_usd=700)
    a._rf = RFt(5.0); rng = random.Random(seed); b = 70; tgt, at = 0.0, -10 ** 9; units = 0.0; fills = collections.deque(); roll = worst = 0.0; tot = 0.0
    for t in range(0, days * DAY, step):
        a._sec = t
        if trend: mid = 100.0 * (1 + trend / 1e4) ** (t / 60) * (1 + rng.uniform(-1, 1) / 1e4); a._rf.p = rng.choice((5.0, 0.0))   # steady rise + flickering signal: slices and rebuilds trade separately
        else: mid = 100.0 * (1 + swing / 1e4 * (1 if (t // 300) % 2 else -1)) * (1 + rng.uniform(-2, 2) / 1e4); a._rf.p = rng.choice((5.0, 5.0, -5.0))
        tgt, at = a._rev_copy_step(b, tgt, at, mid, a._rf.p if t - at >= sstep else None)
        gap = tgt - units
        if abs(gap) * mid < 1: continue
        if abs(tgt) > abs(units) and a._paced_out(b): continue
        q = min(abs(gap), 700 / mid); units += q if gap > 0 else -q; v = q * mid; fill(a, b, t, v, True); fills.append((t, v)); roll += v; tot += v
        while fills and fills[0][0] <= t - DAY: roll -= fills.popleft()[1]
        worst = max(worst, roll)
    return worst, tot
for sd, sw in ((1, 12.0), (2, 30.0), (3, 7.0)):
    w, tot = copy_attack(sd, swing=sw)
    check(f"copy full path, signals every 60 s, price swinging ±{sw:.0f} bp", w < CAP, f"worst 24h ${w:,.0f} of ${CAP:,.0f} | 3-day total ${tot:,.0f}")
for sd, tr in ((4, 3.0), (5, 10.0), (6, 1.0)):
    w, tot = copy_attack(sd, trend=tr, sstep=65)   # 65 s vs the 120-s slice clock: slice and re-add land on different steps, so both trade
    check(f"copy full path, MAX CHURN (steady rise {tr:.0f} bp/min: slice every 120 s, rebuild every 60 s)", w < CAP and tot > 3 * 300000, f"worst 24h ${w:,.0f} of ${CAP:,.0f} | 3-day total ${tot:,.0f} (must show the gate is what holds it)")

# §1279 $300-book ladder: resting levels + the validator's 5-instructions-per-book limit
class _Ins:
    def __init__(s, kind, book, side=None, price=None, oid=None): s.kind, s.bookId, s.side, s.price, s.oid = kind, book, side, price, oid
class _Resp:
    def __init__(s): s.instructions = []
    def limit_order(s, book_id, direction, quantity, price, **k): s.instructions.append(_Ins("place", book_id, direction, price))
    def cancel_order(s, book_id, order_id): s.instructions.append(_Ins("cancel", book_id, oid=order_id))
class _O:
    def __init__(s, i, side, price): s.id, s.side, s.price = i, side, price
L = agent(new_path, pace_cap=450000, mk_vol_lad="2:5:10", mk_vol_lad_size=0.07)
Bd, Sd = L._vol_ladder.__globals__["OrderDirection"].BUY, L._vol_ladder.__globals__["OrderDirection"].SELL
rng = random.Random(5); worst = 0; urgent_ok = True; tick = 0.01
for trial in range(2000):
    bid = round(299 + rng.randint(-50, 50) * tick, 2); ask = round(bid + rng.randint(1, 8) * tick, 2)
    want = {}
    if rng.random() < 0.9: want[Bd] = bid
    if rng.random() < 0.9: want[Sd] = ask
    orders = [_O(i, rng.choice((Bd, Sd)), round(bid + rng.randint(-20, 20) * tick, 2)) for i in range(rng.randint(0, 9))]
    r = _Resp(); L._vol_ladder(r, 7, orders, dict(want), {}, 5.0, 10.0, tick, 2)
    worst = max(worst, len(r.instructions))
    ahead = {o.id for o in orders if (o.side not in want) or (o.side == Bd and o.price > want[Bd]) or (o.side == Sd and o.price < want[Sd])}
    kinds = [(i.kind, i.oid in ahead if i.kind == "cancel" else None) for i in r.instructions]
    first_non_urgent = next((k for k, x in enumerate(kinds) if not (x[0] == "cancel" and x[1])), len(kinds))
    if any(x[0] == "cancel" and x[1] for x in kinds[first_non_urgent:]): urgent_ok = False
check("ladder: never more than 5 instructions per book (validator limit)", worst <= 5, f"worst {worst} over 2,000 random books")
check("ladder: exposed orders (ahead of the touch / pulled side) are cancelled first", urgent_ok, "priority order kept")
r = _Resp(); orders = [_O(1, Bd, 298.98), _O(2, Bd, 298.95), _O(3, Bd, 298.90), _O(4, Sd, 299.12), _O(5, Sd, 299.15), _O(6, Sd, 299.20)]
L._vol_ladder(r, 7, orders, {Bd: 299.00, Sd: 299.10}, {}, 5.0, 10.0, tick, 2)
check("ladder: resting levels are not re-priced when the touch is where we want it", [i.kind for i in r.instructions] == ["place", "place"], f"{[(i.kind, i.price) for i in r.instructions]}")
r = _Resp(); L._vol_ladder(r, 7, [_O(1, Bd, 298.98), _O(2, Bd, 298.95), _O(3, Bd, 298.90)], {Bd: 299.01}, {}, 5.0, 10.0, tick, 2)
check("ladder: touch moves 1 tick up → ladder rests, only the new touch order", [(i.kind, i.price) for i in r.instructions] == [("place", 299.01)], f"{[(i.kind, i.price) for i in r.instructions]}")
o = []; nid = 100
for step in range(4):
    r = _Resp(); L._vol_ladder(r, 7, list(o), {Bd: 299.00, Sd: 299.10}, {}, 5.0, 10.0, tick, 2)
    for i in r.instructions:
        if i.kind == "place": nid += 1; o.append(_O(nid, i.side, i.price))
check("ladder: fills in all 3 levels per side within a few steps", sorted(x.price for x in o) == [298.9, 298.95, 298.98, 299.0, 299.1, 299.12, 299.15, 299.2], f"{sorted(x.price for x in o)}")

# §1281 fleet pattern on the $300 books (_vol_lazy)
Z = agent(new_path, pace_cap=450000, mk_vol_lad="2", mk_vol_lazy=1, mk_vol_penny=5, mk_vol_keep=20, mk_vol_max=8)
rng = random.Random(9); worst = 0; urgent_ok = True; cap_ok = True
for trial in range(3000):
    bid = round(299 + rng.randint(-50, 50) * tick, 2); ask = round(bid + rng.randint(1, 10) * tick, 2)
    want = {}
    if rng.random() < 0.9: want[Bd] = bid
    if rng.random() < 0.9: want[Sd] = ask
    orders = [_O(i, rng.choice((Bd, Sd)), round(bid + rng.randint(-25, 25) * tick, 2)) for i in range(rng.randint(0, 14))]
    r = _Resp(); Z._vol_lazy(r, 7, orders, dict(want), 12.0, tick, 2); worst = max(worst, len(r.instructions))
    pen = Bd in want and Sd in want and round((ask - bid) / tick) >= 5
    tb = {Bd: round(bid + tick, 2) if pen else bid, Sd: round(ask - tick, 2) if pen else ask}
    ahead = {o.id for o in orders if (o.side not in want) or (o.side == Bd and o.price > tb[Bd]) or (o.side == Sd and o.price < tb[Sd])}
    kinds = [(i.kind, i.oid in ahead if i.kind == "cancel" else None) for i in r.instructions]
    fnu = next((k for k, x in enumerate(kinds) if not (x[0] == "cancel" and x[1])), len(kinds))
    if any(x[0] == "cancel" and x[1] for x in kinds[fnu:]): urgent_ok = False
    if len(r.instructions) < 5:                           # budget not binding: resting count per side must end ≤ 8
        cancelled = {i.oid for i in r.instructions if i.kind == "cancel"}; placed = [i for i in r.instructions if i.kind == "place"]
        for sd in (Bd, Sd):
            left = sum(1 for o in orders if o.side == sd and o.id not in cancelled) + sum(1 for i in placed if i.side == sd)
            if sd in want and left > 8: cap_ok = False
check("fleet pattern: never more than 5 instructions per book", worst <= 5, f"worst {worst} over 3,000 random books")
check("fleet pattern: exposed orders cancelled first", urgent_ok, "priority kept")
check("fleet pattern: at most 8 resting orders per side", cap_ok, "when the budget allows")
r = _Resp(); Z._vol_lazy(r, 7, [], {Bd: 299.00, Sd: 299.06}, 12.0, tick, 2)
check("fleet pattern: spread 6 ticks → one tick inside on both sides", sorted((i.side == Sd, i.price) for i in r.instructions) == [(False, 299.01), (True, 299.05)], f"{[(i.price) for i in r.instructions]}")
r = _Resp(); Z._vol_lazy(r, 7, [], {Bd: 299.00, Sd: 299.03}, 12.0, tick, 2)
check("fleet pattern: spread 3 ticks → at the touch", sorted(i.price for i in r.instructions) == [299.0, 299.03], f"{[(i.price) for i in r.instructions]}")
r = _Resp(); Z._vol_lazy(r, 7, [_O(1, Bd, 298.95), _O(2, Bd, 298.80), _O(3, Sd, 299.20)], {Bd: 299.00, Sd: 299.03}, 12.0, tick, 2)
check("fleet pattern: orders left behind (5 and 20 ticks bid, 17 ticks ask) rest; new touch orders only", [(i.kind, i.price) for i in r.instructions] == [("place", 299.0), ("place", 299.03)], f"{[(i.kind, i.price) for i in r.instructions]}")
r = _Resp(); Z._vol_lazy(r, 7, [_O(1, Bd, 298.78)], {Bd: 299.00, Sd: 299.03}, 12.0, tick, 2)
check("fleet pattern: 22 ticks behind → cancelled after the touch orders", [(i.kind) for i in r.instructions] == ["place", "place", "cancel"], f"{[(i.kind, i.price) for i in r.instructions]}")

# §1286 copy-hold arm: each burst exits REV_COPY_HOLD after entry
h = agent(new_path, pace_cap=450000, rev_copy=1, rev_usd=1500, rev_max_usd=15000, rev_tp_bp=0.0, rev_copy_hold=600, sleeve_step=300); h._rf = RFt(5.0)
h._sec = 0; t_, a_ = h._rev_copy_step(3, 0.0, -10 ** 9, 100.0, 5.0)
h._sec = 300; t_, a_ = h._rev_copy_step(3, t_, a_, 100.0, 5.0)
check("hold: two bursts open", abs(t_ * 100 - 3000) < 1e-6 and len(h._legs[3]) == 2, f"${t_ * 100:,.0f}, legs {len(h._legs[3])}")
h._sec = 599; t2, _ = h._rev_copy_step(3, t_, a_, 100.0, None); check("hold: nothing exits before 600 s", t2 == t_, "599 s")
h._sec = 600; t3, _ = h._rev_copy_step(3, t_, a_, 100.0, None); check("hold: first burst exits at 600 s", abs(t3 * 100 - 1500) < 1e-6 and len(h._legs[3]) == 1, f"${t3 * 100:,.0f}")
h._sec = 900; t4, _ = h._rev_copy_step(3, t3, a_, 100.0, None); check("hold: second burst exits at 900 s → flat", t4 == 0.0 and 3 not in h._legs, "flat")
h._sec = 86300; t5, a5 = h._rev_copy_step(4, 0.0, -10 ** 9, 100.0, 5.0); h._sec_prev = 86300; h._sec = 50; h._clock_check()
check("hold: clock reset shifts leg times", abs(h._legs[4][0][0] - (86300 + 50 - 86300)) < 1e-9, f"leg at {h._legs[4][0][0]}")
h._sec = 649; t6, _ = h._rev_copy_step(4, t5, a5, 100.0, None); h._sec = 650; t7, _ = h._rev_copy_step(4, t6, a5, 100.0, None)
check("hold: after the reset the leg still exits 600 s after entry", t6 != 0.0 and t7 == 0.0, "exit at 650 (entry 50)")
def hold_attack(seed, days=3, step=5):
    a = agent(new_path, pace_cap=450000, rev_copy=1, rev_usd=1500, rev_max_usd=15000, rev_tp_bp=0.0, rev_copy_hold=600, sleeve_step=60, rev_clip_usd=700)
    a._rf = RFt(5.0); rng = random.Random(seed); b = 70; tgt, at = 0.0, -10 ** 9; units = 0.0; fills = collections.deque(); roll = worst = 0.0; tot = 0.0
    for t in range(0, days * DAY, step):
        a._sec = t; mid = 100.0 * (1 + rng.uniform(-3, 3) / 1e4); a._rf.p = rng.choice((5.0, -5.0, 0.0))
        tgt, at = a._rev_copy_step(b, tgt, at, mid, a._rf.p if t - at >= 60 else None)
        gap = tgt - units
        if abs(gap) * mid < 1: continue
        if abs(tgt) > abs(units) and a._paced_out(b): continue
        q = min(abs(gap), 700 / mid); units += q if gap > 0 else -q; v = q * mid; fill(a, b, t, v, True); fills.append((t, v)); roll += v; tot += v
        while fills and fills[0][0] <= t - DAY: roll -= fills.popleft()[1]
        worst = max(worst, roll)
    return worst, tot
for sd in (11, 12):
    w, tot = hold_attack(sd)
    check("hold: 3-day full path, signals every 60 s, exits every 600 s", w < CAP and tot > 3 * 300000, f"worst 24h ${w:,.0f} of ${CAP:,.0f} | 3-day ${tot:,.0f}")

# §1293 batched cancel: pulling many orders is ONE instruction
class _RespB:
    def __init__(s): s.instructions = []
    def cancel_order(s, book_id, order_id): s.instructions.append(("one", book_id, order_id))
    def cancel_orders(s, book_id, order_ids): s.instructions.append(("many", book_id, tuple(order_ids)))
cb = agent(new_path, pace_cap=450000); r = _RespB(); cb._cancel_all(r, 7, [_O(i, Bd, 299.0) for i in range(8)])
check("batched cancel: 8 orders → 1 instruction", len(r.instructions) == 1 and r.instructions[0][0] == "many" and len(r.instructions[0][2]) == 8, f"{len(r.instructions)} instruction(s)")
r = _RespB(); cb._cancel_all(r, 7, [_O(1, Bd, 299.0)]); check("batched cancel: 1 order → plain cancel", r.instructions == [("one", 7, 1)], f"{r.instructions}")
r = _RespB(); cb._cancel_all(r, 7, []); check("batched cancel: no orders → nothing", r.instructions == [], "none")

# §1295 calm-book distance: MK_CALM_HS half-spreads from the mid, away from the mid, never more aggressive than the normal target
cz = agent(new_path, pace_cap=450000, mk_calm_hs=1.67)
nb, na = cz._calm_px(30.00, 30.02, 0.01, 2, 30.00, 30.02)
check("calm: 2-tick spread → one tick behind the touch", (nb, na) == (29.99, 30.03), f"{nb} / {na}")
nb, na = cz._calm_px(30.00, 30.06, 0.01, 2, 30.00, 30.06)
check("calm: 6-tick spread → 1.67 hs out (mid 30.03 ∓ 0.05)", (nb, na) == (29.98, 30.08), f"{nb} / {na}")
nb, na = cz._calm_px(30.00, 30.02, 0.01, 2, 29.97, 30.05)
check("calm: never more aggressive than the normal target", (nb, na) == (29.97, 30.05), f"{nb} / {na}")
nb, na = cz._calm_px(30.00, 30.02, 0.01, 2, None, 30.02)
check("calm: a pulled side stays pulled", nb is None and na == 30.03, f"{nb} / {na}")
off = agent(new_path, pace_cap=450000); check("calm: off by default", off.mk_calm_hs == 0.0, "0")

# §1303 calm-book ladder reuses _vol_ladder with its own levels
CL = agent(new_path, pace_cap=450000, mk_calm_lad="1:2:4", mk_calm_lad_size=0.036)
o = []; nid = 500
for step in range(4):
    r = _Resp(); CL._vol_ladder(r, 80, list(o), {Bd: 30.00, Sd: 30.02}, {}, 60.0, 60.0, tick, 2, levels=CL.mk_calm_lad)
    for i in r.instructions:
        if i.kind == "place": nid += 1; o.append(_O(nid, i.side, i.price))
check("calm ladder: touch + 1/2/4 ticks behind on both sides", sorted(x.price for x in o) == [29.96, 29.98, 29.99, 30.0, 30.02, 30.03, 30.04, 30.06], f"{sorted(x.price for x in o)}")
worst = 0
for trial in range(1500):
    bid = round(30 + rng.randint(-30, 30) * tick, 2); ask = round(bid + rng.randint(1, 6) * tick, 2)
    orders = [_O(i, rng.choice((Bd, Sd)), round(bid + rng.randint(-12, 12) * tick, 2)) for i in range(rng.randint(0, 10))]
    r = _Resp(); CL._vol_ladder(r, 80, orders, {Bd: bid, Sd: ask}, {}, 60.0, 60.0, tick, 2, levels=CL.mk_calm_lad); worst = max(worst, len(r.instructions))
check("calm ladder: never more than 5 instructions per book", worst <= 5, f"worst {worst} over 1,500 random books")

# §1311 calm-book order expiry (fleet calm orders rest up to ≈ 500 s; ours expired at 60 s)
class _InsE:
    def __init__(s, kind, price, expiry): s.kind, s.price, s.expiry = kind, price, expiry
class _RespE:
    def __init__(s): s.instructions = []
    def limit_order(s, book_id, direction, quantity, price, **k): s.instructions.append(_InsE("place", price, k.get("expiryPeriod")))
    def cancel_order(s, book_id, order_id): s.instructions.append(_InsE("cancel", None, None))
CE = agent(new_path, pace_cap=450000, mk_calm_lad="1:2:4", mk_calm_lad_size=0.036, mk_calm_expiry=500)
r = _RespE(); CE._vol_ladder(r, 80, [], {Bd: 30.00, Sd: 30.02}, {}, 60.0, 60.0, tick, 2, levels=CE.mk_calm_lad, expiry=CE.mk_calm_expiry or None)
ex = {getattr(i, "expiry", None) for i in r.instructions if i.kind == "place"}
check("calm expiry: every calm ladder order gets 500 s", ex == {500_000_000_000}, f"{ex}")
r = _RespE(); CL._vol_ladder(r, 80, [], {Bd: 30.00, Sd: 30.02}, {}, 60.0, 60.0, tick, 2, levels=CL.mk_calm_lad, expiry=CL.mk_calm_expiry or None)
ex = {getattr(i, "expiry", None) for i in r.instructions if i.kind == "place"}
check("calm expiry: off by default → the normal 60 s", ex == {CL.expiry} and CL.mk_calm_expiry == 0, f"{ex}")
r = _RespE(); IN0 = agent(new_path, pace_cap=450000, mk_vol_lad="2:5:10", mk_calm_expiry=500); IN0._vol_ladder(r, 7, [], {Bd: 299.00, Sd: 299.03}, {}, 5.0, 10.0, tick, 2)
ex = {getattr(i, "expiry", None) for i in r.instructions if i.kind == "place"}
check("calm expiry: $300 ladder keeps 60 s", ex == {IN0.expiry}, f"{ex}")

# §1313 fleet-style 4-dec quoting: ahead of the OTHERS' best (never our own), one deep order, ≤ 5 instructions
class _Lv:
    def __init__(s, price, quantity): s.price, s.quantity = price, quantity
class _Bk:
    def __init__(s, bids, asks): s.bids, s.asks = [_Lv(*x) for x in bids], [_Lv(*x) for x in asks]
class _OQ:
    def __init__(s, i, side, price, quantity): s.id, s.side, s.price, s.quantity = i, side, price, quantity
DC = agent(new_path, pace_cap=450000, mk_dec_size=0.09, mk_dec_inside=1, mk_dec_deep=0.27); t4 = 0.0001
bk = _Bk([(298.0000, 5.0), (297.9990, 8.0)], [(298.1000, 4.0)])
check("dec: others' best ignores none of theirs", DC._others_best(bk, []) == (298.0, 298.1), f"{DC._others_best(bk, [])}")
bk = _Bk([(298.0001, 5.0), (298.0000, 8.0)], [(298.1000, 4.0)])
check("dec: our own best bid is removed from the others' best", DC._others_best(bk, [_OQ(1, Bd, 298.0001, 5.0)]) == (298.0, 298.1), f"{DC._others_best(bk, [_OQ(1, Bd, 298.0001, 5.0)])}")
w = {Bd: 298.0, Sd: 298.1}; k = DC._dec_targets(_Bk([(298.0, 5.0)], [(298.1, 4.0)]), [], w, t4, 4)
check("dec: one tick ahead of the others on both sides; deep = 0.27 spreads", w == {Bd: 298.0001, Sd: 298.0999} and k == 270, f"{w} k {k}")
w = {Bd: 297.95, Sd: 298.1}; DC._dec_targets(_Bk([(298.0, 5.0)], [(298.1, 4.0)]), [], w, t4, 4)
check("dec: a side skewed behind the touch stays put", w[Bd] == 297.95 and w[Sd] == 298.0999, f"{w}")
w = {Bd: 298.0, Sd: 298.0002}; k = DC._dec_targets(_Bk([(298.0, 5.0)], [(298.0002, 4.0)]), [], w, t4, 4)
check("dec: 2-tick spread → no move, falls back", k is None and w == {Bd: 298.0, Sd: 298.0002}, f"{w} {k}")
# no walking: our order becomes the best each round; the target must stay the same price
orders = []; prices = []
for rnd in range(6):
    bb = sorted([(298.0, 5.0)] + [(o.price, o.quantity) for o in orders if o.side == Bd], key=lambda x: -x[0])
    aa = sorted([(298.1, 4.0)] + [(o.price, o.quantity) for o in orders if o.side == Sd], key=lambda x: x[0])
    bk = _Bk(bb, aa); w = {Bd: bb[0][0], Sd: aa[0][0]}; k = DC._dec_targets(bk, orders, w, t4, 4)
    r = _RespE(); DC._vol_ladder(r, 110, list(orders), w, {}, 15.0, 15.0, t4, 4, levels=[k], tol=max(1, k // 2))
    for i in r.instructions:
        if i.kind == "place": orders.append(_OQ(1000 + len(orders), Bd if i.price < 298.05 else Sd, i.price, 15.0))
    prices.append(max(o.price for o in orders if o.side == Bd))
check("dec: never steps inside its own order (no walk)", len(set(prices)) == 1 and prices[0] == 298.0001 and len(orders) == 4, f"best bids {prices}, orders {len(orders)}")
deep = sorted(o.price for o in orders if o.side == Bd)[0]
check("dec: deep bid 270 ticks behind the touch target", abs(deep - (298.0001 - 0.027)) < 1e-9, f"{deep}")
worst = 0
for trial in range(1500):
    bid = round(298 + rng.randint(-500, 500) * t4, 4); ask = round(bid + rng.randint(3, 1500) * t4, 4)
    ords = [_OQ(i, rng.choice((Bd, Sd)), round(bid + rng.randint(-600, 600) * t4, 4), 15.0) for i in range(rng.randint(0, 8))]
    w = {Bd: bid, Sd: ask}; k = DC._dec_targets(_Bk([(bid, 5.0)], [(ask, 5.0)]), ords, w, t4, 4)
    if k is None: continue
    r = _RespE(); DC._vol_ladder(r, 110, ords, w, {}, 15.0, 15.0, t4, 4, levels=[k], tol=max(1, k // 2)); worst = max(worst, len(r.instructions))
    assert all(i.price is None or i.price > 0 for i in r.instructions)
check("dec: never more than 5 instructions per book", worst <= 5, f"worst {worst} over 1,500 random books")
off = agent(new_path, pace_cap=450000); check("dec: off by default", off.mk_dec_size == 0.0, "0")

# §1314 $300 inside quoting must step inside the OTHERS' best, not our own order (no walk over rounds)
IW = agent(new_path, pace_cap=450000, mk_vol_lad="2:5:10", mk_vol_inside=5); ords = []; best = []
for rnd in range(8):
    bb = sorted([(299.00, 5.0)] + [(o.price, o.quantity) for o in ords if o.side == Bd], key=lambda x: -x[0])
    aa = sorted([(299.08, 5.0)] + [(o.price, o.quantity) for o in ords if o.side == Sd], key=lambda x: x[0])
    bk = _Bk(bb, aa); w = {Bd: bb[0][0], Sd: aa[0][0]}
    r = _RespE(); IW._vol_ladder(r, 7, list(ords), w, {}, 5.0, 10.0, tick, 2, inside=5, obest=IW._others_best(bk, ords))
    for i in r.instructions:
        if i.kind == "place": ords.append(_OQ(5000 + len(ords), Bd if i.price < 299.04 else Sd, i.price, 5.0))
    best.append((max(o.price for o in ords if o.side == Bd), min(o.price for o in ords if o.side == Sd)))
check("inside fix: one tick ahead of the others every round (no walk)", set(best) == {(299.01, 299.07)}, f"{sorted(set(best))}")
w = {Bd: 299.00, Sd: 299.03}; r = _RespE(); IW._vol_ladder(r, 7, [], w, {}, 5.0, 10.0, tick, 2, inside=5, obest=(299.00, 299.03))
check("inside fix: 3-tick spread → stays at the touch", (299.0 in [i.price for i in r.instructions]) and (299.03 in [i.price for i in r.instructions]), f"{[i.price for i in r.instructions]}")
w = {Bd: 298.97, Sd: 299.08}; r = _RespE(); IW._vol_ladder(r, 7, [], w, {}, 5.0, 10.0, tick, 2, inside=5, obest=(299.00, 299.08))
pl = [i.price for i in r.instructions if i.kind == "place"]
check("inside fix: a skewed-back bid stays back; the ask still steps inside", 298.97 in pl and 299.07 in pl, f"{pl}")

# §1317 calm hold + soft pace gate (fleet calm orders rest ≈ 107 s and are filled as the price comes to them)
PH = agent(new_path, pace_cap=450000, pace_steady=450000, pace_start=100000, mk_calm_lad="1:2:3", mk_pace_hold=5000, mk_calm_hold=2)
bk = _Bk([(30.00, 9.0), (29.99, 5.0)], [(30.02, 9.0)])
ords = [_OQ(1, Bd, 30.00, 3.0), _OQ(2, Bd, 29.99, 3.0), _OQ(3, Bd, 29.98, 3.0), _OQ(4, Sd, 30.02, 3.0), _OQ(5, Sd, 30.04, 3.0), _OQ(6, Bd, 30.01, 3.0)]
dr = sorted(o.id for o in PH._pace_hold_drop(bk, ords, 0.01))
check("soft gate: pulls touch + inside orders only, deep ones stay", dr == [1, 4, 6], f"drop {dr}")
PH._sec = 1000; PH._tok[80] = [-100.0, 1000]
check("soft gate: calm book, small debt → hold", PH._pace_hold_ok(80) is True, "bucket -100")
PH._tok[80] = [-6000.0, 1000]; check("soft gate: debt past −mk_pace_hold → full cancel", PH._pace_hold_ok(80) is False, "bucket -6000")
PH._tok[7] = [-100.0, 1000]; check("soft gate: $300 book → full cancel", PH._pace_hold_ok(7) is False, "book 7")
PH._tok[81] = [-100.0, 1000]; PH._pace[81] = [(900, 450000.0)]; check("soft gate: 24-h ledger at pace_cap → full cancel", PH._pace_hold_ok(81) is False, "ledger 450k")
check("soft gate + hold: off by default", agent(new_path, pace_cap=450000).mk_pace_hold == 0 and agent(new_path, pace_cap=450000).mk_calm_hold == 0, "0")
# hold: target moved 1 tick behind our resting touch bid → keep it, no new touch bid; 3 ticks → cancel
o = [_OQ(10, Bd, 30.00, 3.0)]; r = _RespE(); w = {Bd: 29.99, Sd: 30.02}
PH._vol_ladder(r, 80, list(o), w, {}, 60.0, 60.0, 0.01, 2, levels=PH.mk_calm_lad, hold=2, obest=(30.00, 30.02))
check("hold: target 1 tick behind → resting bid kept, no new touch bid", not any(i.kind == "cancel" for i in r.instructions) and 29.99 not in [i.price for i in r.instructions if i.kind == "place"], f"{[(i.kind, i.price) for i in r.instructions]}")
r = _RespE(); w = {Bd: 29.97, Sd: 30.02}
PH._vol_ladder(r, 80, list(o), w, {}, 60.0, 60.0, 0.01, 2, levels=PH.mk_calm_lad, hold=2, obest=(30.00, 30.02))
check("hold: target 3 ticks behind → cancelled", any(i.kind == "cancel" for i in r.instructions), f"{[(i.kind, i.price) for i in r.instructions]}")
o2 = [_OQ(11, Bd, 30.01, 3.0)]; r = _RespE(); w = {Bd: 30.00, Sd: 30.02}
PH._vol_ladder(r, 80, list(o2), w, {}, 60.0, 60.0, 0.01, 2, levels=PH.mk_calm_lad, hold=2, obest=(30.00, 30.02))
check("hold: an order inside the others' best is not held", any(i.kind == "cancel" for i in r.instructions), f"{[(i.kind, i.price) for i in r.instructions]}")
# CAP: adversary fills every order whenever the gate is open AND drains the resting deep orders (3 per side x $1.8k) every second the soft gate holds
def attack_hold(a, days=3, seed=3, order=1800.0):
    rng = random.Random(seed); b = 80; fills = collections.deque(); roll = worst = 0.0
    for t in range(0, days * DAY, 1):
        a._sec = t
        if a._paced_out(b):
            if not a._pace_hold_ok(b): continue
            v = 6 * order                                       # worst case: every resting deep order filled at once
        else:
            v = order * rng.uniform(1.0, 2.0) * 2
        fill(a, b, t, v, True); fills.append((t, v)); roll += v
        while fills and fills[0][0] <= t - DAY: roll -= fills.popleft()[1]
        worst = max(worst, roll)
    return worst
for sd in (3, 4):
    w_ = attack_hold(agent(new_path, pace_cap=450000, pace_steady=450000, pace_start=100000, mk_pace_hold=5000, mk_calm_hold=2), seed=sd)
    check(f"CAP soft gate (seed {sd}): worst rolling 24 h under $500k", w_ < 500000, f"${w_:,.0f}")

# §1323 no-chase + calm no-touch
NC = agent(new_path, pace_cap=450000, mk_nochase_bp=1.0, mk_nochase_s=10)
for sec in range(100, 111):
    NC._sec = sec; w = {Bd: 299.00 + (0.05 if sec >= 108 else 0.0), Sd: 299.08 + (0.05 if sec >= 108 else 0.0)}
    n = NC._nochase(7, w, w[Bd], w[Sd], (w[Bd] + w[Sd]) / 2, 2)
check("no-chase: bid rose 5 ticks (1.7 bp) in 10 s → our bid stays at the old best; the ask is not capped", w[Bd] == 299.0 and w[Sd] == 299.13 and n == 1, f"{w} n {n}")
NF = agent(new_path, pace_cap=450000, mk_nochase_bp=1.0, mk_nochase_s=10)
for sec in range(100, 111):
    NF._sec = sec; w = {Bd: 299.00, Sd: 299.08}; n = NF._nochase(7, w, 299.00, 299.08, 299.04, 2)
check("no-chase: flat book → unchanged", w == {Bd: 299.0, Sd: 299.08} and n == 0, f"{w}")
NA = agent(new_path, pace_cap=450000, mk_nochase_bp=1.0, mk_nochase_s=10)
for sec in range(100, 111):
    NA._sec = sec; b_ = 299.00 - (0.05 if sec >= 108 else 0.0); w = {Bd: b_, Sd: b_ + 0.08}; n = NA._nochase(7, w, b_, b_ + 0.08, b_ + 0.04, 2)
check("no-chase: ask fell 5 ticks → our ask stays at the old best; the bid is not capped", w[Sd] == 299.08 and w[Bd] == 298.95 and n == 1, f"{w} n {n}")
NY = agent(new_path, pace_cap=450000, mk_nochase_bp=1.0, mk_nochase_s=10); NY._sec = 100; w = {Bd: 299.05, Sd: 299.13}
check("no-chase: no history 10 s back yet → unchanged", NY._nochase(7, w, 299.05, 299.13, 299.09, 2) == 0 and w[Bd] == 299.05, f"{w}")
check("no-chase + no-touch: off by default", agent(new_path, pace_cap=450000).mk_nochase_bp == 0 and agent(new_path, pace_cap=450000).mk_calm_touch_min == 0, "0")
CT = agent(new_path, pace_cap=450000, mk_calm_lad="1:2:3", mk_calm_touch_min=3)
r = _RespE(); CT._vol_ladder(r, 80, [_OQ(20, Bd, 30.00, 3.0)], {Bd: 30.00, Sd: 30.02}, {}, 60.0, 60.0, 0.01, 2, levels=CT.mk_calm_lad, no_touch=True)
pl = sorted(i.price for i in r.instructions if i.kind == "place"); cn = sum(1 for i in r.instructions if i.kind == "cancel")
check("calm no-touch: resting touch bid cancelled, only ladder orders placed (none at 30.00 / 30.02)", cn == 1 and 30.0 not in pl and 30.02 not in pl and 29.99 in pl and 30.03 in pl, f"cancel {cn} place {pl}")
worst = 0
for trial in range(1500):
    bid = round(30 + rng.randint(-30, 30) * 0.01, 2); ask = round(bid + rng.randint(1, 6) * 0.01, 2)
    ords = [_OQ(i, rng.choice((Bd, Sd)), round(bid + rng.randint(-8, 8) * 0.01, 2), 3.0) for i in range(rng.randint(0, 10))]
    r = _RespE(); CT._vol_ladder(r, 80, ords, {Bd: bid, Sd: ask}, {}, 60.0, 60.0, 0.01, 2, levels=CT.mk_calm_lad, no_touch=rng.random() < 0.5, hold=2, obest=(bid, ask))
    worst = max(worst, len(r.instructions))
check("calm no-touch + hold: never more than 5 instructions per book", worst <= 5, f"worst {worst} over 1,500 random books")
had = bool(NC._bbo); NC._sec_prev = 86000; NC._sec = 50; NC._clock_check()
check("no-chase: a sim-day reset clears the best-price history", had and not NC._bbo, f"had {had}, after {dict(NC._bbo)}")

# §1326 no-chase history is recorded while a book is paced out (via _bbo_rec), so the cap fires on the first quote after the block
NP = agent(new_path, pace_cap=450000, mk_nochase_bp=1.0, mk_nochase_s=10)
for sec in range(100, 115):
    NP._sec = sec; NP._bbo_rec(7, 299.00 + (0.05 if sec >= 110 else 0.0), 299.08 + (0.05 if sec >= 110 else 0.0))   # paced out: only recorded
NP._sec = 115; w = {Bd: 299.05, Sd: 299.13}; n = NP._nochase(7, w, 299.05, 299.13, 299.09, 2)
check("no-chase: history kept through a pace block → first quote after it is capped", w[Bd] == 299.0 and n == 1, f"{w} n {n}")

# §1328 flow pull on the $300 books only: check the gating expression the main path uses
FV = agent(new_path, pace_cap=450000, flow_pull_vol_only=1)
on = lambda a, b: bool(a.flow_pull and not (a.flow_pull_vol_only and b >= 63))
check("flow_pull_vol_only: on for $300 books, off for calm / 4-dec", on(FV, 7) and not on(FV, 80) and not on(FV, 110), "7 on, 80/110 off")
check("flow_pull_vol_only: off by default (pull everywhere as before)", on(agent(new_path, pace_cap=450000), 80), "80 on")
src = open(new_path).read()
check("flow_pull_vol_only: main path uses the same gate", "fp_on = self.flow_pull and not (self.flow_pull_vol_only and self._g(book_id) != \"vol\")" in src and "if fp_on and near > self.flow_pull" in src, "gate present")

# §1332 4-dec: a touch order left behind by a price move must NOT be kept as a ladder order (pile-up); real cancel ids applied
class _RespC:
    def __init__(s): s.instructions = []
    def limit_order(s, book_id, direction, quantity, price, **k): s.instructions.append(("place", direction, price))
    def cancel_order(s, book_id, order_id): s.instructions.append(("cancel", order_id, None))
    def cancel_orders(s, book_id, ids): s.instructions.append(("cancels", list(ids), None))
DP = agent(new_path, pace_cap=450000, mk_dec_size=0.09, mk_dec_inside=1, mk_dec_deep=0.27); ords = []; nid = 9000
for rnd in range(10):                                     # the others' best rises 20 ticks per round; we are never filled
    ob = round(298.0 + rnd * 0.002, 4); oa = round(ob + 0.1, 4)
    bk = _Bk(sorted([(ob, 5.0)] + [(o.price, o.quantity) for o in ords if o.side == Bd], key=lambda x: -x[0]), sorted([(oa, 5.0)] + [(o.price, o.quantity) for o in ords if o.side == Sd], key=lambda x: x[0]))
    w = {Bd: bk.bids[0].price, Sd: bk.asks[0].price}; k = DP._dec_targets(bk, ords, w, 0.0001, 4)
    r = _RespC(); DP._vol_ladder(r, 110, list(ords), w, {}, 15.0, 15.0, 0.0001, 4, levels=[k], tol=max(1, k // 2))
    gone = {x for kind, a_, _ in r.instructions if kind == "cancel" for x in [a_]} | {x for kind, a_, _ in r.instructions if kind == "cancels" for x in a_}
    ords = [o for o in ords if o.id not in gone]
    for kind, d, px in r.instructions:
        if kind == "place": nid += 1; ords.append(_OQ(nid, d, px, 15.0))
per_side = max(sum(1 for o in ords if o.side == Bd), sum(1 for o in ords if o.side == Sd))
check("4-dec: no pile-up of left-behind touch orders over 10 rising rounds", per_side <= 3, f"max {per_side} resting orders per side")
cn = _RespE(); o7 = [_OQ(i, Bd, round(298.0 - i * 0.0010, 4), 15.0) for i in range(7)]
DP._vol_ladder(cn, 110, o7, {Bd: 298.0, Sd: 298.1}, {}, 15.0, 15.0, 0.0001, 4, levels=[270], tol=135)
check("4-dec: 7 stale orders → at most 5 instructions in one reply", len(cn.instructions) <= 5, f"{len(cn.instructions)} instructions")

# §1334 $300 no-touch: gate expression + ladder-only behaviour on a $300 book
VT = agent(new_path, pace_cap=450000, mk_vol_lad="2:5:10", mk_vol_touch_min=4)
src = open(new_path).read()
check("vol no-touch: main path gate present", "nt_v = bool(self.mk_vol_touch_min and ob_v" in src and "no_touch=nt_v" in src, "gate")
r = _RespE(); VT._vol_ladder(r, 7, [_OQ(30, Bd, 299.00, 5.0)], {Bd: 299.00, Sd: 299.03}, {}, 5.0, 10.0, 0.01, 2, no_touch=True)
pl = sorted(i.price for i in r.instructions if i.kind == "place"); cn = sum(1 for i in r.instructions if i.kind == "cancel")
check("vol no-touch: touch bid cancelled, only 2/5/10 ladder placed", cn == 1 and 299.0 not in pl and 299.03 not in pl and 298.98 in pl and 299.05 in pl, f"cancel {cn} place {pl}")
check("vol no-touch: off by default", agent(new_path, pace_cap=450000).mk_vol_touch_min == 0, "0")

# §1342 live settings reload: whitelisted quoting knobs only; pacing/cap never; bad files change nothing
import tempfile as _tf, time as _tm
lpd = _tf.mkdtemp(); lpf = os.path.join(lpd, "lp.json")
LP = agent(new_path, pace_cap=450000, pace_steady=450000, live_params=lpf, live_params_s=30)
LP._sec = 1000; LP._live_reload()
check("live: no file → nothing changes", LP.flow_pull == 0.3, f"flow_pull {LP.flow_pull}")
json.dump({"flow_pull": 0, "mk_vol_inside": 5, "pace_cap": 999999, "pace_steady": 900000, "mk_vol_size": 0.5, "mk_calm_expiry": 300}, open(lpf, "w"))
LP._sec = 1040; LP._live_reload()
check("live: whitelisted knobs applied", LP.flow_pull == 0.0 and LP.mk_vol_inside == 5 and LP.mk_calm_expiry == 300_000_000_000, f"flow_pull {LP.flow_pull} inside {LP.mk_vol_inside} expiry {LP.mk_calm_expiry}")
check("live: pacing / cap settings can NOT change", LP.pace_cap == 450000 and LP.pace_rate == 450000 / 86400, f"pace_cap {LP.pace_cap} rate {LP.pace_rate:.3f}")
check("live: out-of-range size ignored", getattr(LP, "mk_vol_size", 0.0) != 0.5, f"mk_vol_size {getattr(LP, 'mk_vol_size', None)}")
_tm.sleep(0.01); open(lpf, "w").write("{broken"); os.utime(lpf, None)
LP._sec = 1080; LP._live_reload()
check("live: broken file → values unchanged", LP.flow_pull == 0.0 and LP.mk_vol_inside == 5, f"flow_pull {LP.flow_pull} inside {LP.mk_vol_inside}")
_tm.sleep(0.01); json.dump({"flow_pull": 0.3}, open(lpf, "w")); os.utime(lpf, None)
LP._sec = 1090; LP._live_reload()
check("live: not re-read sooner than live_params_s", LP.flow_pull == 0.0, f"flow_pull {LP.flow_pull} at +10 s")
LP._sec = 50; LP._live_reload()                                # sim-day reset: clock went back
check("live: works after a sim-day reset (clock back)", LP.flow_pull == 0.3, f"flow_pull {LP.flow_pull}")
check("live: off by default", agent(new_path, pace_cap=450000).live_params == "", "''")

# §1346 live ladder levels
LL = agent(new_path, pace_cap=450000, mk_calm_lad="1:2:4", mk_vol_lad="2:5:10", live_params=lpf, live_params_s=30)
_tm.sleep(0.01); json.dump({"mk_calm_lad": "1:2:3", "mk_vol_lad": "3:6:10"}, open(lpf, "w")); os.utime(lpf, None)
LL._sec = 5000; LL._live_reload()
check("live ladders: applied as sorted int lists", LL.mk_calm_lad == [1, 2, 3] and LL.mk_vol_lad == [3, 6, 10], f"{LL.mk_calm_lad} {LL.mk_vol_lad}")
_tm.sleep(0.01); json.dump({"mk_calm_lad": "1:2:3:4:5", "mk_vol_lad": "0:40"}, open(lpf, "w")); os.utime(lpf, None)
LL._sec = 5100; LL._live_reload()
check("live ladders: > 4 levels or out-of-range ticks ignored", LL.mk_calm_lad == [1, 2, 3] and LL.mk_vol_lad == [3, 6, 10], f"{LL.mk_calm_lad} {LL.mk_vol_lad}")
r = _RespE(); LL._vol_ladder(r, 80, [], {Bd: 30.00, Sd: 30.02}, {}, 60.0, 60.0, 0.01, 2, levels=LL.mk_calm_lad)
check("live ladders: new calm levels used by the ladder (≤ 5 instructions)", len(r.instructions) <= 5 and 29.99 in [i.price for i in r.instructions], f"{[i.price for i in r.instructions]}")

# §1369 live fundamental lean / micro weight (range-checked)
LF = agent(new_path, pace_cap=450000, live_params=lpf, live_params_s=30)
_tm.sleep(0.01); json.dump({"fund": 0.5, "micro": 0.5}, open(lpf, "w")); os.utime(lpf, None)
LF._sec = 7000; LF._live_reload()
check("live fund/micro: applied", LF.fund == 0.5 and LF.micro == 0.5, f"fund {LF.fund} micro {LF.micro}")
_tm.sleep(0.01); json.dump({"fund": 3.0}, open(lpf, "w")); os.utime(lpf, None)
LF._sec = 7100; LF._live_reload()
check("live fund: out of range (> 1) ignored", LF.fund == 0.5, f"fund {LF.fund}")

# §1378 fund lean clipped to ±fund_cap × spread
FC = agent(new_path, pace_cap=450000, live_params=lpf, live_params_s=30, fund=0.3)
check("fund cap: off by default (unclipped lean)", abs(FC._fund_shift(310.0, 300.0, 0.02) - 3.0) < 1e-9, f"{FC._fund_shift(310.0, 300.0, 0.02)}")
_tm.sleep(0.01); json.dump({"fund": 0.3, "fund_cap": 0.5}, open(lpf, "w")); os.utime(lpf, None)
FC._sec = 7500; FC._live_reload()
check("fund cap: live-applied", FC.fund_cap == 0.5, f"fund_cap {FC.fund_cap}")
check("fund cap: big lean clipped to +0.5 spread", abs(FC._fund_shift(310.0, 300.0, 0.02) - 0.01) < 1e-9, f"{FC._fund_shift(310.0, 300.0, 0.02)}")
check("fund cap: big negative lean clipped to -0.5 spread", abs(FC._fund_shift(290.0, 300.0, 0.02) + 0.01) < 1e-9, f"{FC._fund_shift(290.0, 300.0, 0.02)}")
check("fund cap: small lean unchanged", abs(FC._fund_shift(300.02, 300.0, 0.06) - 0.006) < 1e-9, f"{FC._fund_shift(300.02, 300.0, 0.06)}")
_tm.sleep(0.01); json.dump({"fund_cap": 9.0}, open(lpf, "w")); os.utime(lpf, None)
FC._sec = 7600; FC._live_reload()
check("fund cap: out of range (> 5) ignored", FC.fund_cap == 0.5, f"fund_cap {FC.fund_cap}")

# §1379 fundamental MOVE lean ($300 only, windowed, clipped)
FM = agent(new_path, pace_cap=450000, live_params=lpf, live_params_s=30, fund_mv=0.5, fund_mv_s=10, fund_mv_cap=1.0)
FM._sec = 100; FM._fund_rec(7, 300.00); FM._fund_rec(80, 300.00)
FM._sec = 105; FM._fund_rec(7, 300.10)
check("fund move: no shift before a full window", FM._fund_mv_shift(7, 0.06) == 0.0, f"{FM._fund_mv_shift(7, 0.06)}")
FM._sec = 110; FM._fund_rec(7, 300.04); FM._fund_rec(80, 300.04)
check("fund move: shift = 0.5 × Δf over 10 s", abs(FM._fund_mv_shift(7, 0.06) - 0.02) < 1e-9, f"{FM._fund_mv_shift(7, 0.06)}")
check("fund move: calm books untouched by default", FM._fund_mv_shift(80, 0.06) == 0.0, f"{FM._fund_mv_shift(80, 0.06)}")
FM._sec = 120; FM._fund_rec(7, 301.00)
check("fund move: clipped to +1 spread", abs(FM._fund_mv_shift(7, 0.06) - 0.06) < 1e-9, f"{FM._fund_mv_shift(7, 0.06)}")
FM._sec = 125; FM._fund_rec(7, 299.00)
check("fund move: clipped to −1 spread", abs(FM._fund_mv_shift(7, 0.06) + 0.06) < 1e-9, f"{FM._fund_mv_shift(7, 0.06)}")
check("fund move: window keeps ≤ 10 s of history", FM._fh[7][0][0] >= 125 - 10 - 5, f"{FM._fh[7]}")
check("fund move: off by default", agent(new_path, pace_cap=450000).fund_mv == 0.0, "0")
_tm.sleep(0.01); json.dump({"fund_mv": 0.3, "fund_mv_cap": 0.5}, open(lpf, "w")); os.utime(lpf, None)
FM._sec = 9000; FM._live_reload()
check("fund move: live-applied", FM.fund_mv == 0.3 and FM.fund_mv_cap == 0.5, f"{FM.fund_mv} {FM.fund_mv_cap}")
_tm.sleep(0.01); json.dump({"fund_mv": 5.0}, open(lpf, "w")); os.utime(lpf, None)
FM._sec = 9100; FM._live_reload()
check("fund move: out of range (> 2) ignored", FM.fund_mv == 0.3, f"{FM.fund_mv}")

# §1380 fund level lean scope
FS = agent(new_path, pace_cap=450000, live_params=lpf, live_params_s=30)
check("fund scope: default all books", FS._fund_in_scope(5) and FS._fund_in_scope(80) and FS._fund_in_scope(120), "0")
_tm.sleep(0.01); json.dump({"fund_scope": 1}, open(lpf, "w")); os.utime(lpf, None)
FS._sec = 9500; FS._live_reload()
check("fund scope 1: calm only", FS.fund_scope == 1 and FS._fund_in_scope(63) and FS._fund_in_scope(101) and not FS._fund_in_scope(62) and not FS._fund_in_scope(102), f"{FS.fund_scope}")
_tm.sleep(0.01); json.dump({"fund_scope": 2}, open(lpf, "w")); os.utime(lpf, None)
FS._sec = 9600; FS._live_reload()
check("fund scope 2: $300 only", FS._fund_in_scope(0) and FS._fund_in_scope(62) and not FS._fund_in_scope(63), f"{FS.fund_scope}")
_tm.sleep(0.01); json.dump({"fund_scope": 7}, open(lpf, "w")); os.utime(lpf, None)
FS._sec = 9700; FS._live_reload()
check("fund scope: out of range ignored", FS.fund_scope == 2, f"{FS.fund_scope}")

# §1398 4-dec deep-only + second deep level
DT = agent(new_path, pace_cap=450000, live_params=lpf, live_params_s=30, mk_dec_size=0.09, mk_dec_deep=0.27)
check("dec deep2: off by default → one level", DT._dec_levels(8, 30) == [8], f"{DT._dec_levels(8, 30)}")
_tm.sleep(0.01); json.dump({"mk_dec_touch": 0, "mk_dec_deep2": 0.6}, open(lpf, "w")); os.utime(lpf, None)
DT._sec = 9800; DT._live_reload()
check("dec touch/deep2: live-applied", DT.mk_dec_touch == 0 and DT.mk_dec_deep2 == 0.6, f"{DT.mk_dec_touch} {DT.mk_dec_deep2}")
check("dec deep2: second level 0.6 spreads back", DT._dec_levels(8, 30) == [8, 18], f"{DT._dec_levels(8, 30)}")
check("dec deep2: second level at least K+2", DT._dec_levels(8, 10) == [8, 10], f"{DT._dec_levels(8, 10)}")
r = _Resp(); DT._vol_ladder(r, 110, [], {Bd: 1.0000, Sd: 1.0030}, {}, 5.0, 5.0, 0.0001, 4, levels=[8, 18], tol=4, no_touch=True)
pl = sorted(round(i.price, 4) for i in r.instructions if i.kind == "place")
check("dec deep-only: no order at the touch, deep levels placed", 1.0 not in pl and 1.003 not in pl and len(pl) >= 2, f"{pl}")
_tm.sleep(0.01); json.dump({"mk_dec_touch": 5}, open(lpf, "w")); os.utime(lpf, None)
DT._sec = 9900; DT._live_reload()
check("dec touch: out of range ignored", DT.mk_dec_touch == 0, f"{DT.mk_dec_touch}")

# §1403 book_map (layout changes between sim days: 256 books on 11-12)
BM = agent(new_path, pace_cap=450000, live_params=lpf, live_params_s=30)
check("book_map: legacy ranges by default", [BM._g(b) for b in (0, 62, 63, 101, 102, 127, 200)] == ["vol", "vol", "calm", "calm", "dec", "dec", "dec"], f"{[BM._g(b) for b in (0, 62, 63, 101, 102, 127, 200)]}")
_tm.sleep(0.01); json.dump({"book_map": "calm:63-101;dec:192-255"}, open(lpf, "w")); os.utime(lpf, None)
BM._sec = 10000; BM._live_reload()
check("book_map: live-applied (102-191 → vol, 192-255 dec)", [BM._g(b) for b in (0, 70, 110, 150, 191, 192, 255)] == ["vol", "calm", "vol", "vol", "vol", "dec", "dec"], f"{[BM._g(b) for b in (0, 70, 110, 150, 191, 192, 255)]}")
_tm.sleep(0.01); json.dump({"book_map": "bogus:1-2"}, open(lpf, "w")); os.utime(lpf, None)
BM._sec = 10100; BM._live_reload()
check("book_map: bad spec ignored (map unchanged)", BM._g(150) == "vol" and BM._g(200) == "dec", f"{BM._g(150)} {BM._g(200)}")
_tm.sleep(0.01); json.dump({"book_map": ""}, open(lpf, "w")); os.utime(lpf, None)
BM._sec = 10200; BM._live_reload()
check("book_map: empty → legacy again", BM._g(110) == "dec" and BM._g(70) == "calm", f"{BM._g(110)} {BM._g(70)}")

# §1414 "low" group ($30 books) with its own size / ladder overrides
LO = agent(new_path, pace_cap=450000, live_params=lpf, live_params_s=30, mk_vol_size=0.022, mk_vol_lad="1:2:4:7", mk_vol_lad_size=0.027)
_tm.sleep(0.01); json.dump({"book_map": "calm:63-101;low:128-191;dec:192-255"}, open(lpf, "w")); os.utime(lpf, None)
LO._sec = 11000; LO._live_reload()
check("low group: low books quote as vol", LO._g(150) == "vol" and LO._is_low(150) and not LO._is_low(10) and LO._g(200) == "dec", f"{LO._g(150)} {LO._is_low(150)}")
check("low group: no overrides until set", LO._low_ov(150) is None, f"{LO._low_ov(150)}")
_tm.sleep(0.01); json.dump({"book_map": "calm:63-101;low:128-191;dec:192-255", "mk_low_size": 0.036, "mk_low_lad": "1:2:3", "mk_low_lad_size": 0.04}, open(lpf, "w")); os.utime(lpf, None)
LO._sec = 11100; LO._live_reload()
check("low group: overrides live-applied", LO._low_ov(150) == {"mk_vol_size": 0.036, "mk_vol_lad_size": 0.04, "mk_vol_lad": [1, 2, 3]} and LO._low_ov(10) is None, f"{LO._low_ov(150)}")
seen = {}
LO._quote_inner = lambda r, b, bk, ac: seen.update({b: (LO.mk_vol_size, list(LO.mk_vol_lad), LO.mk_vol_lad_size)})
LO._quote(None, 150, None, None); LO._quote(None, 10, None, None)
check("low group: overrides only inside a low book, restored after", seen[150] == (0.036, [1, 2, 3], 0.04) and seen[10] == (0.022, [1, 2, 4, 7], 0.027) and LO.mk_vol_size == 0.022, f"{seen}")
_tm.sleep(0.01); json.dump({"mk_low_size": 0.5}, open(lpf, "w")); os.utime(lpf, None)
LO._sec = 11200; LO._live_reload()
check("low group: out-of-range size ignored", LO.mk_low_size == 0.036, f"{LO.mk_low_size}")

# §1373 live $300 off switch
LS = agent(new_path, pace_cap=450000, live_params=lpf, live_params_s=30)
_tm.sleep(0.01); json.dump({"mk_skip_vol": 1}, open(lpf, "w")); os.utime(lpf, None)
LS._sec = 8000; LS._live_reload()
check("live $300 off: mk_skip_vol applied", LS.mk_skip_vol == 1, f"mk_skip_vol {LS.mk_skip_vol}")
r = _RespE(); LS._vol_ladder(r, 7, [_OQ(1, Bd, 299.0, 5.0), _OQ(2, Sd, 299.06, 5.0)], {}, {}, 5.0, 10.0, 0.01, 2, levels=[2, 5, 10, 20])
check("live $300 off: an empty want cancels resting $300 orders, places none", sum(1 for i in r.instructions if i.kind == "cancel") == 2 and not any(i.kind == "place" for i in r.instructions), f"{[(i.kind, i.price) for i in r.instructions]}")

# §1304 $300 inside quoting inside _vol_ladder
IN = agent(new_path, pace_cap=450000, mk_vol_lad="2:5:10", mk_vol_inside=5)
r = _Resp(); IN._vol_ladder(r, 7, [], {Bd: 299.00, Sd: 299.06}, {}, 5.0, 10.0, tick, 2, inside=5)
pl = sorted((i.side == Sd, i.price) for i in r.instructions if i.kind == "place")
check("inside: 6-tick spread → touch orders one tick inside", (False, 299.01) in pl and (True, 299.05) in pl, f"{pl}")
r = _Resp(); IN._vol_ladder(r, 7, [], {Bd: 299.00, Sd: 299.03}, {}, 5.0, 10.0, tick, 2, inside=5)
pl = sorted((i.side == Sd, i.price) for i in r.instructions if i.kind == "place")
check("inside: 3-tick spread → stays at the touch", (False, 299.0) in pl and (True, 299.03) in pl, f"{pl}")
r = _Resp(); IN._vol_ladder(r, 7, [], {Bd: 299.00}, {}, 5.0, 10.0, tick, 2, inside=5)
check("inside: one side pulled → no inside move", all(i.price != 299.01 for i in r.instructions if i.kind == "place"), "bid stays 299.00")
r = _Resp(); IN._vol_ladder(r, 7, [], {Bd: 299.00, Sd: 299.06}, {}, 5.0, 10.0, tick, 2)
check("inside: off unless asked", all(i.price not in (299.01, 299.05) for i in r.instructions if i.kind == "place"), "default 0")

# §1308 trade-flow pull helper
TF = agent(new_path, pace_cap=450000, mk_tflow_usd=1000, mk_tflow_win=10); TF._sec = 100
TF._sflow = {7: {91: 5.0, 95: 3.0, 99: 2.0, 85: 50.0}}
check("trade flow: sums only the last 10 sim s, in $", abs(TF._tflow_usd(7, 300.0) - 3000.0) < 1e-6, f"${TF._tflow_usd(7, 300.0):,.0f} (85 s is outside)")
TF._sflow = {7: {95: -4.0}}; check("trade flow: sellers give a negative sum", TF._tflow_usd(7, 300.0) < 0, f"${TF._tflow_usd(7, 300.0):,.0f}")
check("trade flow: off by default", agent(new_path, pace_cap=450000).mk_tflow_usd == 0.0, "0")
print("ALL PASS" if not bad else f"{bad} FAILED")
