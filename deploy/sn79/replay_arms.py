import argparse, glob, json, sys, tempfile, importlib.util
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.protocol import MarketSimulationStateUpdate
def load(p):
    s = importlib.util.spec_from_file_location("Q" + str(abs(hash(p))), p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
bodies = [open(p).read() for p in sorted(glob.glob("/opt/mvtrx/cap/req_*.json"))]
def run(path, **kw):
    cfg = argparse.Namespace(size=0.01, skew=6.0, max_inv=0.05, edge=1, model="/opt/mvtrx/agents/model30_of.json", alpha_k=1.0, join=1, pull=1.0,
                             max_units=20, lazy_load=1, lean=1, raw=1, cancel_first=1, data_dir=tempfile.mkdtemp(), **kw)
    a = load(path).QuoteAgent(93, cfg, tempfile.mkdtemp()); out = []
    for b in bodies:
        s = MarketSimulationStateUpdate(**json.loads(b)); s.decompress(lazy=True)
        r = a.handle(s); out.append([json.dumps(i.model_dump(), sort_keys=True, default=str) for i in r.instructions])
    return out
live = run("/opt/mvtrx/agents/QuoteAgent.py")
noarm = run("/opt/mvtrx/QuoteAgent.arms.py")
same = run("/opt/mvtrx/QuoteAgent.arms.py", arms="edge:1/edge:1/edge:1")
real = run("/opt/mvtrx/QuoteAgent.arms.py", arms="edge:2/edge:3/flow_pull:0.3+flow_win:10+flow_cool:3")
print("no arms identical to live:", noarm == live)
print("identity arms identical to live:", same == live)
book = lambda i: json.loads(i).get("bookId")
diff_books = {book(i) for a, b in zip(live, real) for i in set(a) ^ set(b)}
print("books whose instructions changed under real arms:", len(diff_books), "| any in arm 0 (book % 4 == 0):", any(b % 4 == 0 for b in diff_books if b is not None))
