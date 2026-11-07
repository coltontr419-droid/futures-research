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
print("ALL PASS" if not bad else f"{bad} FAILED")
