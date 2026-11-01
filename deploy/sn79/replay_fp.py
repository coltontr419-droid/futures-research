import argparse, glob, json, sys, tempfile, importlib.util
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.protocol import MarketSimulationStateUpdate
def load(p):
    s = importlib.util.spec_from_file_location("Q" + str(abs(hash(p))), p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
bodies = [open(p).read() for p in sorted(glob.glob("/opt/mvtrx/cap/req_*.json"))] * 3
def run(path, fp):
    cfg = argparse.Namespace(size=0.01, skew=6.0, max_inv=0.05, edge=1, model="/opt/mvtrx/agents/model30_of.json", alpha_k=1.0, join=1, pull=1.0,
                             max_units=20, lazy_load=1, lean=1, raw=1, flow_pull=fp, data_dir=tempfile.mkdtemp())
    a = load(path).QuoteAgent(93, cfg, tempfile.mkdtemp()); out = []
    for b in bodies:
        s = MarketSimulationStateUpdate(**json.loads(b)); s.decompress(lazy=True)
        r = a.handle(s); out.append(sorted(json.dumps(i.model_dump(), sort_keys=True, default=str) for i in r.instructions))
    return out
live = run("/opt/mvtrx/agents/QuoteAgent.py", 0.0); new0 = run("/opt/mvtrx/QuoteAgent.fp.py", 0.0); new3 = run("/opt/mvtrx/QuoteAgent.fp.py", 0.3)
print("flow_pull=0 identical to live agent:", new0 == live)
lim = lambda o: sum(1 for st in o for i in st if "price" in i and "quantity" in i and "cancel" not in i.lower())
print("instructions live", sum(map(len, live)), "| flow_pull=0.3", sum(map(len, new3)))
