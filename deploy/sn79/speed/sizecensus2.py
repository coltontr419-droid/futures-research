"""Census for the redo: seed per-second mid + fundamental histories so the model predicts BUY on even vol books and SELL on odd ones; full buckets; settings
mk_model_lean 1, fund_mv 0, mk_gate 3, mk_gate_side 1, mk_lad_off 1. Per group/side: new order size and ticks behind the others' best; jumped sides."""
import sys, json, glob, tempfile, argparse, importlib.util, subprocess, os, collections, statistics as st
from collections import deque
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
ARMS = {"A now": {}, "B size": dict(mk_vol_size=0.072, mk_calm_size=0.072, mk_rest_frac=0.1)}
for on, tk in [(k, t) for t in (4700.0, 3000.0, 800.0) for k in ARMS]:
    tmp = tempfile.mkdtemp(); P = dict(P0); P.update(tape="", pace_ledger="", lock_dir="", data_dir=tmp, model_lean_file="/opt/mvtrx/agents/model_lean.json", model_lean_30_file="/opt/mvtrx/agents/model_lean_30.json")
    L = json.load(open("/opt/mvtrx/live_params_255.json")); L.update(ARMS[on]); json.dump(L, open(f"{tmp}/lp.json", "w")); P["live_params"] = f"{tmp}/lp.json"
    spec = importlib.util.spec_from_file_location("QAM%s%d" % (on[0], int(tk)), sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    a = mod.QuoteAgent(174, argparse.Namespace(**P), tempfile.mkdtemp())
    s = MarketSimulationStateUpdate(**json.loads(open(body).read())); s.decompress(lazy=True); sec = s.timestamp // 10**9
    for bk_s, d in s.books._raw_books.items():
        bk = int(bk_s)
        if bk >= 128 or not d.get("b") or not d.get("a"): continue
        a._tok[bk] = [tk, sec]
        if bk % 2: continue
        m = (d["b"][0]["p"] + d["a"][0]["p"]) / 2; F = d.get("f") or m; sg = 1   # +1: want BUY (price fell, fundamental rising, fund above mid)
        a._mh[bk] = deque([(sec - 300, m * (1 + sg * 0.002)), (sec - 50, m * (1 + sg * 0.001)), (sec - 10, m * (1 + sg * 0.0002))])
        a._fh2[bk] = deque([(sec - 300, F * (1 - sg * 0.002)), (sec - 60, F * (1 - sg * 0.001)), (sec - 30, F * (1 - sg * 0.0005))])
        a._tok[bk] = [tk, sec]
    sys.stdout = dn; r = a.handle(s); sys.stdout = real
    R = collections.defaultdict(list); J = collections.Counter()
    for bk in range(128):
        book = a._books.get(bk); acct = a.accounts.get(bk)
        if book is None or acct is None: continue
        g = a._g(bk) + (" LEAN" if bk % 2 == 0 else " no-lean"); want_side = 0
        for sd in a._jumped.get(bk, ()): J[(g, "jumped = predicted" if int(sd) == want_side else "jumped = OTHER")] += 1
        ob, oa = a._others_best(book, acct.orders)
        for i in r.instructions or []:
            if getattr(i, "bookId", None) != bk or not hasattr(i, "price") or not getattr(i, "postOnly", False) or not (ob and oa): continue
            sd = int(i.direction); d_ = round(((ob - i.price) if sd == 0 else (i.price - oa)) / 0.01)
            R[(g, "BID" if sd == 0 else "ASK")].append((i.price * i.quantity, d_))
    print(f"--- {on} bucket ${tk:,.0f}: jumps {dict(J)} | books with no order: {sum(1 for bk in range(128) if a._g(bk) in ('vol','calm') and not any(getattr(i,'bookId',None)==bk and hasattr(i,'price') for i in r.instructions or []) and not a.accounts.get(bk) is None and not (a.accounts.get(bk).orders))}")
    for k, v in sorted(R.items()):
        print(f"   {k[0]:13} {k[1]:4}: new orders {len(v):3d} | size median ${st.median(x[0] for x in v):,.0f} | ticks behind others' best median {st.median(x[1] for x in v):+.0f} | size max ${max(x[0] for x in v):,.0f}")
