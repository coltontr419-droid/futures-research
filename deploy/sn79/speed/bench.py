"""Benchmark an agent file on captured validator requests with the live x2 unit params + live_params_174.json.
python bench.py <agent.py> [reps] [prof]   -> per phase medians: decompress, update, respond, report; optional cProfile of handle."""
import sys, json, glob, time, tempfile, argparse, importlib.util, statistics as st, cProfile, pstats, io, shutil, subprocess, os
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.protocol import MarketSimulationStateUpdate
path = sys.argv[1]; reps = int(sys.argv[2]) if len(sys.argv) > 2 else 3; prof = len(sys.argv) > 3 and sys.argv[3] == "prof"
ex = subprocess.run(["systemctl", "show", "-p", "ExecStart", "--value", "mvtrx-x2"], capture_output=True, text=True).stdout
args = ex.split("--agent.params", 1)[1].split(";", 1)[0].split()
P = {}
for a in args:
    if "=" not in a: break
    k, v = a.split("=", 1)
    try: v = int(v)
    except ValueError:
        try: v = float(v)
        except ValueError: pass
    P[k] = v
tmp = tempfile.mkdtemp()
P["tape"] = os.environ.get("TAPE", f"{tmp}/tape.jsonl"); P["pace_ledger"] = ""; P["lock_dir"] = f"{tmp}/locks"; os.makedirs(P["lock_dir"])
shutil.copy("/opt/mvtrx/live_params_174.json", f"{tmp}/lp.json"); P["live_params"] = f"{tmp}/lp.json"
for k, v in [kv.split("=", 1) for kv in os.environ.get("OVR", "").split()]: P[k] = float(v) if v.replace(".", "").lstrip("-").isdigit() else v
P["data_dir"] = tempfile.mkdtemp()
bodies = [open(p).read() for p in sorted(glob.glob("/opt/mvtrx/cap14/req_*.json"))]
spec = importlib.util.spec_from_file_location("QA_bench", path); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
import bittensor as bt
bt.logging.set_warning() if hasattr(bt.logging, "set_warning") else None
devnull = open(os.devnull, "w"); real_stdout = sys.stdout
agent = mod.QuoteAgent(174, argparse.Namespace(**P), tempfile.mkdtemp())
T = {"decomp": [], "update": [], "respond": [], "report": [], "total": []}; nins = []
ou, orp, orep = agent.update, agent.respond_simulation, agent.report
def tw(name, fn):
    def w(*a, **k):
        t = time.perf_counter(); r = fn(*a, **k); T[name].append(time.perf_counter() - t); return r
    return w
agent.update, agent.respond_simulation, agent.report = tw("update", ou), tw("respond", orp), tw("report", orep)
syns = []
for rep in range(reps):
    for b in bodies:
        s = MarketSimulationStateUpdate(**json.loads(b))
        t0 = time.perf_counter(); s.decompress(lazy=True); T["decomp"].append(time.perf_counter() - t0)
        sys.stdout = devnull
        t1 = time.perf_counter(); r = agent.handle(s); T["total"].append(time.perf_counter() - t1)
        sys.stdout = real_stdout
        nins.append(len(getattr(r, "instructions", None) or []))
        if rep == reps - 1: syns.append(b)
print(f"{os.path.basename(path)}: books {len(s.books._raw_books)} | instructions/reply median {st.median(nins)}")
for k, v in T.items(): print(f"  {k:8} median {1e3 * st.median(v):6.1f} ms  p90 {1e3 * sorted(v)[int(len(v) * .9)]:6.1f}")
if prof:
    ss = []
    for b in syns:
        s = MarketSimulationStateUpdate(**json.loads(b)); s.decompress(lazy=True); ss.append(s)
    pr = cProfile.Profile(); sys.stdout = devnull; pr.enable()
    for s in ss: agent.handle(s)
    pr.disable(); sys.stdout = real_stdout
    o = io.StringIO(); pstats.Stats(pr, stream=o).sort_stats("tottime").print_stats(25); print(o.getvalue()[:6000])
