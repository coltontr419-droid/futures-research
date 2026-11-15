import sys, json, glob, tempfile, argparse, importlib.util, shutil, subprocess, os, collections
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
tmp = tempfile.mkdtemp(); P = dict(P0); P.update(tape="", pace_ledger="", lock_dir="", data_dir=tmp)
L = json.load(open("/opt/mvtrx/live_params_179.json")); L["mk_vol_expiry"] = 10; json.dump(L, open(f"{tmp}/lp.json", "w")); P["live_params"] = f"{tmp}/lp.json"
spec = importlib.util.spec_from_file_location("QAX", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
a = mod.QuoteAgent(174, argparse.Namespace(**P), tempfile.mkdtemp()); dn = open(os.devnull, "w"); real = sys.stdout
b = open(sorted(glob.glob("/opt/mvtrx/cap14/req_*.json"))[0]).read()
s = MarketSimulationStateUpdate(**json.loads(b)); s.decompress(lazy=True); sys.stdout = dn; r = a.handle(s); sys.stdout = real
print("live knob value (ns):", a.mk_vol_expiry, "| calm expiry (ns):", a.mk_calm_expiry)
C = collections.Counter()
for i in r.instructions or []:
    e = getattr(i, "expiryPeriod", None)
    if e is None: continue
    bk = i.bookId; g = "calm" if 63 <= bk <= 101 else ("vol" if bk < 128 else ("$30" if bk < 192 else "4dec"))
    C[(g, e // 10**9)] += 1
print(sorted(C.items()))
