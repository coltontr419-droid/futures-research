"""Census for mk_gate: seed half the $300 books' pace buckets LOW (−2,000) and half FULL; one reply; per mode: new touch-side order sizes, distance behind the
others' best, books with both sides quoted. Knob 0 vs 3, mk_lad_off 1 (the redo setting)."""
import sys, json, glob, tempfile, argparse, importlib.util, subprocess, os, collections, statistics as st
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
body = sorted(glob.glob("/opt/mvtrx/cap14/req_*.json"))[0]; dn = open(os.devnull, "w"); real = sys.stdout
for gate in (0, 3):
    tmp = tempfile.mkdtemp(); P = dict(P0); P.update(tape="", pace_ledger="", lock_dir="", data_dir=tmp)
    L = json.load(open("/opt/mvtrx/live_params_179.START.json")); L.update(mk_gate=gate, mk_lad_off=1); json.dump(L, open(f"{tmp}/lp.json", "w")); P["live_params"] = f"{tmp}/lp.json"
    spec = importlib.util.spec_from_file_location("QAG%d" % gate, sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    a = mod.QuoteAgent(174, argparse.Namespace(**P), tempfile.mkdtemp())
    s = MarketSimulationStateUpdate(**json.loads(open(body).read())); s.decompress(lazy=True); sec = s.timestamp // 10**9
    a._sec = sec
    for bk in range(128): a._tok[bk] = [-2000.0 if bk % 2 else 4000.0, sec]
    sys.stdout = dn; r = a.handle(s); sys.stdout = real
    R = collections.defaultdict(list); both = collections.Counter()
    for bk in range(128):
        book = a._books.get(bk); acct = a.accounts.get(bk)
        if book is None or acct is None: continue
        ob, oa = a._others_best(book, acct.orders); mode = "LOW bucket" if bk % 2 else "FULL bucket"; sides = set()
        for i in r.instructions or []:
            if getattr(i, "bookId", None) != bk or not hasattr(i, "price") or not getattr(i, "postOnly", False): continue
            d = round(((ob - i.price) if int(i.direction) == 0 else (i.price - oa)) / 0.01) if (ob and oa) else None
            R[mode].append((i.price * i.quantity, d)); sides.add(int(i.direction))
        both[mode] += len(sides) == 2
    for mode, v in sorted(R.items()):
        print(f"mk_gate {gate} | {mode}: new orders {len(v)} | size median ${st.median(x[0] for x in v):,.0f} | ticks behind others' best median {st.median(x[1] for x in v if x[1] is not None):+.0f} | books with both sides placed {both[mode]}")
