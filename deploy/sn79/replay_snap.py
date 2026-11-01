import argparse, glob, json, sys, tempfile, importlib.util
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.protocol import MarketSimulationStateUpdate
def load(p):
    s = importlib.util.spec_from_file_location("Q" + str(abs(hash(p))), p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
bodies = [open(p).read() for p in sorted(glob.glob("/opt/mvtrx/cap/req_*.json"))]
def run(path, **kw):
    cfg = argparse.Namespace(size=0.01, skew=6.0, max_inv=0.05, edge=1, model="/opt/mvtrx/agents/model30_of.json", alpha_k=1.0, join=1, pull=1.0,
                             max_units=20, lazy_load=1, lean=1, raw=1, sticky=1, data_dir=tempfile.mkdtemp(), **kw)
    a = load(path).QuoteAgent(93, cfg, tempfile.mkdtemp()); out = []; levels = []
    for b in bodies:
        s = MarketSimulationStateUpdate(**json.loads(b)); s.decompress(lazy=True)
        raw = s.books._raw_books
        r = a.handle(s); out.append(sorted(json.dumps(i.model_dump(), sort_keys=True, default=str) for i in r.instructions))
        for i in r.instructions:
            d = i.model_dump()
            if d.get("price") is not None and d.get("bookId") is not None:
                side = int(d.get("direction", d.get("side", 0)))
                lv = raw[int(d["bookId"])]["b" if side == 0 else "a"]
                levels.append(any(abs(l["p"] - d["price"]) < 1e-9 for l in lv))
    return out, levels
live, lv0 = run("/opt/mvtrx/agents/QuoteAgent.py"); new0, _ = run("/opt/mvtrx/QuoteAgent.sn.py"); new1, lv1 = run("/opt/mvtrx/QuoteAgent.sn.py", snap=1)
print("snap=0 identical to live sticky agent:", new0 == live)
print(f"new limit orders placed at a price that already had a level: live {sum(lv0)}/{len(lv0)} ({sum(lv0)/max(1,len(lv0)):.0%}) | snap=1 {sum(lv1)}/{len(lv1)} ({sum(lv1)/max(1,len(lv1)):.0%})")
