"""Run two agent files on the same captured states (each state parsed fresh per agent, REPS passes); compare every reply's instructions
and the full tape. python equiv.py <old.py> <new.py> [reps]"""
import sys, json, glob, time, tempfile, argparse, importlib.util, shutil, subprocess, os, statistics as st
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.protocol import MarketSimulationStateUpdate
old, new = sys.argv[1], sys.argv[2]; reps = int(sys.argv[3]) if len(sys.argv) > 3 else 2
ex = subprocess.run(["systemctl", "show", "-p", "ExecStart", "--value", "mvtrx-x2"], capture_output=True, text=True).stdout
P0 = {}
for a in ex.split("--agent.params", 1)[1].split(";", 1)[0].split():
    if "=" not in a: break
    k, v = a.split("=", 1)
    for f in (int, float):
        try: v = f(v); break
        except ValueError: pass
    P0[k] = v
for kv in os.environ.get("OVR", "").split():
    k, v = kv.split("=", 1); P0[k] = float(v)
bodies = [open(p).read() for p in sorted(glob.glob("/opt/mvtrx/cap14/req_*.json"), key=lambda x: int(x.split("_")[-1].split(".")[0]))]
devnull = open(os.devnull, "w"); real = sys.stdout
def mk(path, tag):
    tmp = tempfile.mkdtemp(); P = dict(P0)
    P["tape"] = f"{tmp}/tape.jsonl"; P["pace_ledger"] = f"{tmp}/ledger"; P["lock_dir"] = f"{tmp}/locks"; shutil.copytree("/opt/mvtrx/locks", P["lock_dir"])
    shutil.copy("/opt/mvtrx/live_params_174.json", f"{tmp}/lp.json"); P["live_params"] = f"{tmp}/lp.json"; P["data_dir"] = tempfile.mkdtemp()
    spec = importlib.util.spec_from_file_location("QA_" + tag, path); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.QuoteAgent(174, argparse.Namespace(**P), tempfile.mkdtemp()), P
A, PA = mk(old, "old"); B, PB = mk(new, "new")
def ser(r):
    out = []
    for i in (getattr(r, "instructions", None) or []):
        d = i.model_dump() if hasattr(i, "model_dump") else vars(i)
        out.append((type(i).__name__, json.dumps(d, sort_keys=True, default=str)))
    return out
diffs = 0; n = 0; TA = []; TB = []
for rep in range(reps):
    for bi, b in enumerate(bodies):
        res = []
        for ag, T in ((A, TA), (B, TB)):
            s = MarketSimulationStateUpdate(**json.loads(b)); s.decompress(lazy=True)
            # vary sim time per pass so pace/clock logic moves forward like a live run
            sys.stdout = devnull; t = time.perf_counter(); r = ag.handle(s); T.append(time.perf_counter() - t); sys.stdout = real
            res.append(ser(r))
        n += 1
        if res[0] != res[1]:
            diffs += 1
            if diffs <= 3:
                a, c = res
                print(f"DIFF pass {rep} state {bi}: {len(a)} vs {len(c)} instructions")
                for x, y in zip(a, c):
                    if x != y: print("  old", x[1][:200]); print("  new", y[1][:200]); break
        time.sleep(0.6)   # let the tape worker finish
time.sleep(1.0)
ta, tb = open(PA["tape"]).read(), open(PB["tape"]).read()
la, lb = open(PA["pace_ledger"]).read() if os.path.exists(PA["pace_ledger"]) else "", open(PB["pace_ledger"]).read() if os.path.exists(PB["pace_ledger"]) else ""
print(f"replies compared {n}, instruction diffs {diffs} | instructions per reply {len(res[0])}")
print(f"tape identical {ta == tb} ({ta.count(chr(10))} vs {tb.count(chr(10))} lines) | pace ledger identical {la == lb} ({la.count(chr(10))} rows)")
print("lock folders identical", sorted(os.listdir(PA["lock_dir"])) == sorted(os.listdir(PB["lock_dir"])), len(os.listdir(PB["lock_dir"])), "files")
if os.environ.get("TRACE"):
    import traceback, collections
    C = collections.Counter(); G = type(B).respond_simulation.__globals__; RB = G["_RawBook"]; orig = RB.events.fget
    def tr(self):
        if self._events is None: C[traceback.extract_stack(limit=3)[0].name + ":" + str(traceback.extract_stack(limit=3)[0].lineno)] += 1
        return orig(self)
    RB.events = property(tr); B.tape_async = 0
    s = MarketSimulationStateUpdate(**json.loads(bodies[0])); s.decompress(lazy=True); sys.stdout = devnull; B.handle(s); sys.stdout = real
    print("events built from lines", dict(C))
print(f"handle median old {1e3*st.median(TA):.1f} ms new {1e3*st.median(TB):.1f} ms | max old {1e3*max(TA):.1f} new {1e3*max(TB):.1f}")
