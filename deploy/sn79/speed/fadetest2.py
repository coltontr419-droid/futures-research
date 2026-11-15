"""Sanity: with mk_fade_lean on and a seeded mid history (price FELL over 60/300 s → fade says BUY), the $300 vol-book jump goes to the BUY side; seeded RISE → SELL;
knob 0 → no change vs the fundamental-move path."""
import sys, json, glob, tempfile, argparse, importlib.util, subprocess, os, collections
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.protocol import MarketSimulationStateUpdate
from collections import deque
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
def run(knob, shift):
    tmp = tempfile.mkdtemp(); P = dict(P0); P.update(tape="", pace_ledger="", lock_dir="", data_dir=tmp, pace_cap=0)
    L = json.load(open("/opt/mvtrx/live_params_179.START.json")); L["mk_fade_lean"] = knob; L["fund_mv"] = float(os.environ.get("FMV", "0")); json.dump(L, open(f"{tmp}/lp.json", "w")); P["live_params"] = f"{tmp}/lp.json"
    spec = importlib.util.spec_from_file_location("QAF%s%s" % (knob, shift), sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    a = mod.QuoteAgent(174, argparse.Namespace(**P), tempfile.mkdtemp())
    s = MarketSimulationStateUpdate(**json.loads(open(bodies[0]).read())); s.decompress(lazy=True); sec = s.timestamp // 10**9
    raw = s.books._raw_books
    for bk, d in raw.items():
        bk = int(bk)
        if bk < 63 or 101 < bk < 128:
            b, a_ = d["b"][0]["p"], d["a"][0]["p"]; m = (b + a_) / 2
            a._mh[bk] = deque([(sec - 300, m * (1 + shift)), (sec - 60, m * (1 + shift))])   # shift > 0: price was HIGHER → it fell → fade BUY
            if os.environ.get("FCONF"):                      # fundamental moved AGAINST the fade: fade BUY (price fell) while the fundamental FELL further → fair shifts down
                f = d.get("f") or m; fs = float(os.environ["FCONF"])
                a._fh[bk] = [(sec - 11, f * (1 + fs * (1 if shift > 0 else -1))), (sec - 1, f)]
    sys.stdout = dn; a.handle(s); sys.stdout = real
    return a
for knob, shift, want in ((1.0, 0.001, "BUY"), (1.0, -0.001, "SELL"), (0.0, 0.001, "none (fund_mv 0 → no lean)")):
    a = run(knob, shift); J = collections.Counter()
    for bk, sides in a._jumped.items():
        for sd in sides: J[str(sd).split(".")[-1]] += 1
    print(f"mk_fade_lean {knob} seeded move {'fell' if shift > 0 else 'rose'} 10 bp → jumped sides {dict(J)} (expected {want})")
