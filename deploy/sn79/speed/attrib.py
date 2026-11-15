"""EXACT code attribution (no market model): run the real agent on captured states with one rule switched off at a time; after the last reply, where do
our $300 quotes sit vs the OTHER makers' best?  python attrib.py <agent.py>"""
import sys, json, glob, tempfile, argparse, importlib.util, shutil, subprocess, os, statistics as st
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.protocol import MarketSimulationStateUpdate
ex = subprocess.run(["systemctl", "show", "-p", "ExecStart", "--value", "mvtrx-x2"], capture_output=True, text=True).stdout
P0 = {}
for a in ex.split("--agent.params", 1)[1].split(";", 1)[0].split():
    if "=" not in a: break
    k, v = a.split("=", 1)
    for f in (int, float):
        try: v = f(v); break
        except ValueError: pass
    P0[k] = v
bodies = [open(p).read() for p in sorted(glob.glob("/opt/mvtrx/cap14/req_*.json"), key=lambda x: int(x.split("_")[-1].split(".")[0]))]
LP0 = json.load(open("/opt/mvtrx/live_params_179.START.json"))
dn = open(os.devnull, "w"); real = sys.stdout
def run(name, lp=None, unit=None):
    tmp = tempfile.mkdtemp(); P = dict(P0); P.update(unit or {})
    P["tape"] = ""; P["pace_ledger"] = ""; P["lock_dir"] = ""; L = dict(LP0); L.update(lp or {}); json.dump(L, open(f"{tmp}/lp.json", "w")); P["live_params"] = f"{tmp}/lp.json"; P["data_dir"] = tmp
    spec = importlib.util.spec_from_file_location("QA" + name, sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    a = mod.QuoteAgent(174, argparse.Namespace(**P), tempfile.mkdtemp())
    for rep in range(2):
        for b in bodies:
            s = MarketSimulationStateUpdate(**json.loads(b)); s.decompress(lazy=True); sys.stdout = dn; r = a.handle(s); sys.stdout = real
    tick = 0.01; at = ins = tot = none = 0; behind = []
    for bk in range(128):
        book = a._books.get(bk); acct = a.accounts.get(bk)
        if book is None or acct is None: continue
        canc = set(); new = {0: [], 1: []}
        for i in (r.instructions or []):
            if getattr(i, "bookId", None) != bk: continue
            for c in getattr(i, "cancellations", None) or []: canc.add(c.orderId)
            if hasattr(i, "price") and getattr(i, "postOnly", False): new[int(i.direction)].append(i.price)
        rest = {0: [o.price for o in acct.orders if o.id not in canc and int(o.side) == 0] + new[0], 1: [o.price for o in acct.orders if o.id not in canc and int(o.side) == 1] + new[1]}
        ob, oa = a._others_best(book, acct.orders)
        for side, oth in ((0, ob), (1, oa)):
            if oth is None: continue
            tot += 1
            if not rest[side]: none += 1; continue
            best = max(rest[side]) if side == 0 else min(rest[side])
            d = round(((oth - best) if side == 0 else (best - oth)) / tick)   # ticks behind the others' best (<0 = inside)
            behind.append(d); at += d <= 0; ins += d < 0
    print(f"{name:34} $300 sides {tot}: at/inside others' best {at / tot:4.0%} | strictly inside {ins / tot:4.0%} | no order {none / tot:4.0%} | median ticks behind {st.median(behind):+.0f}")
run("START (live)")
run("fee-aware OFF (mk_fee_k 0)", lp={"mk_fee_k": 0.0})
run("skew 0", lp={"skew": 0})
run("no-chase OFF", lp={"mk_nochase_bp": 0})
run("fund lean OFF (fund_mv 0)", lp={"fund_mv": 0.0})
run("pacing OFF (pace_cap 0)", unit={"pace_cap": 0})
run("all five OFF", lp={"mk_fee_k": 0.0, "skew": 0, "mk_nochase_bp": 0, "fund_mv": 0.0}, unit={"pace_cap": 0})
