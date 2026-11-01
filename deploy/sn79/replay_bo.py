import argparse, glob, json, sys, tempfile, importlib.util
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.protocol import MarketSimulationStateUpdate
def load(p):
    s = importlib.util.spec_from_file_location("Q" + str(abs(hash(p))), p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
bodies = [open(p).read() for p in sorted(glob.glob("/opt/mvtrx/cap/req_*.json"))]   # one pass: the clock must not run backwards (cooldowns)
def run(path, fp, **kw):
    cfg = argparse.Namespace(size=0.01, skew=6.0, max_inv=0.05, edge=1, model="/opt/mvtrx/agents/model30_of.json", alpha_k=1.0, join=1, pull=1.0,
                             max_units=20, lazy_load=1, lean=1, raw=1, flow_pull=fp, **kw, data_dir=tempfile.mkdtemp())
    a = load(path).QuoteAgent(93, cfg, tempfile.mkdtemp()); out = []
    for b in bodies:
        s = MarketSimulationStateUpdate(**json.loads(b)); s.decompress(lazy=True)
        r = a.handle(s); out.append(sorted(json.dumps(i.model_dump(), sort_keys=True, default=str) for i in r.instructions))
    return out
live = run("/opt/mvtrx/agents/QuoteAgent.py", 0.3); new = run("/opt/mvtrx/QuoteAgent.bo.py", 0.3)
strong = run("/opt/mvtrx/QuoteAgent.bo.py", 0.3, flow_win=10, flow_cool=3)
print("defaults identical to live flow_pull agent:", new == live)
print("instructions live", sum(map(len, live)), "| window 10 s + cooldown 3 s", sum(map(len, strong)))
