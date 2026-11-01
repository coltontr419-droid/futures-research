import argparse, glob, json, sys, tempfile, importlib.util
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.protocol import MarketSimulationStateUpdate
def load(p):
    s = importlib.util.spec_from_file_location("Q" + str(abs(hash(p))), p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
bodies = [open(p).read() for p in sorted(glob.glob("/opt/mvtrx/cap/req_*.json"))]
def run(path, **kw):
    tape = tempfile.mktemp()
    cfg = argparse.Namespace(size=0.01, skew=6.0, max_inv=0.05, edge=1, model="/opt/mvtrx/agents/model30_of.json", alpha_k=1.0, join=1, pull=1.0,
                             max_units=20, lazy_load=1, lean=1, raw=1, sticky=1, tape=tape, data_dir=tempfile.mkdtemp(), **kw)
    a = load(path).QuoteAgent(93, cfg, tempfile.mkdtemp()); out = []
    for b in bodies:
        s = MarketSimulationStateUpdate(**json.loads(b)); s.decompress(lazy=True)
        r = a.handle(s); out.append(sorted(json.dumps(i.model_dump(), sort_keys=True, default=str) for i in r.instructions))
    return out, tape
live, _ = run("/opt/mvtrx/agents/QuoteAgent.py"); new, tape = run("/opt/mvtrx/QuoteAgent.q.py", qlog=1)
print("instructions identical to live sticky agent:", new == live)
Q = [json.loads(l) for l in open(tape) if '"queue"' in l]
print("queue lines", len(Q), "| example", Q[0] if Q else None)
ahead = [x[2] / x[3] for r in Q for x in r["queue"] if x[3] > 0]
import statistics; print("share of level size ahead of our orders: median %.2f, mean %.2f, n %d" % (statistics.median(ahead), statistics.mean(ahead), len(ahead)))
