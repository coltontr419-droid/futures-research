"""Census: after replying to the 5 captured states (2 passes), our resting + new orders per $300 book side, with mk_lad_off 0 vs 1; books with an order on BOTH sides."""
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
bodies = sorted(glob.glob("/opt/mvtrx/cap14/req_*.json"), key=lambda x: int(x.split("_")[-1].split(".")[0]))
dn = open(os.devnull, "w"); real = sys.stdout
for knob in (0, 1):
    tmp = tempfile.mkdtemp(); P = dict(P0); P.update(tape="", pace_ledger="", lock_dir="", data_dir=tmp)
    L = json.load(open("/opt/mvtrx/live_params_179.START.json")); L["mk_lad_off"] = knob; json.dump(L, open(f"{tmp}/lp.json", "w")); P["live_params"] = f"{tmp}/lp.json"
    spec = importlib.util.spec_from_file_location("QAL%d" % knob, sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    a = mod.QuoteAgent(174, argparse.Namespace(**P), tempfile.mkdtemp())
    for rep in range(2):
        for b in bodies:
            s = MarketSimulationStateUpdate(**json.loads(open(b).read())); s.decompress(lazy=True); sys.stdout = dn; r = a.handle(s); sys.stdout = real
    per = []; both = 0; usd = []; tot = 0
    for bk in range(128):
        acct = a.accounts.get(bk); book = a._books.get(bk)
        if acct is None or book is None: continue
        canc = set(); new = collections.Counter(); newusd = []
        for i in r.instructions or []:
            if getattr(i, "bookId", None) != bk: continue
            for c in getattr(i, "cancellations", None) or []: canc.add(c.orderId)
            if hasattr(i, "price") and getattr(i, "postOnly", False): new[int(i.direction)] += 1; newusd.append(i.price * i.quantity)
        cnt = collections.Counter(int(o.side) for o in acct.orders if o.id not in canc); cnt.update(new)
        tot += 1; per += [cnt[0], cnt[1]]; both += cnt[0] > 0 and cnt[1] > 0; usd += newusd
    print(f"mk_lad_off {knob}: $300 books {tot} | orders per side median {st.median(per):.0f} max {max(per)} | books with BOTH sides quoted {both} | new order size median ${st.median(usd) if usd else 0:,.0f} (n {len(usd)})")
