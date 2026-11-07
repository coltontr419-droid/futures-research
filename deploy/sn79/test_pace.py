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
print("ALL PASS" if not bad else f"{bad} FAILED")
