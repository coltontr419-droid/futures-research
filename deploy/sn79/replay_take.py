"""Replay the captured live states (cap/req_*.json) through the live QuoteAgent and the take build (§1211 addendum 5): take=0 must give the
live agent's instructions exactly; take=4 with the prediction forced to ±5 ticks must add one IOC limit per book at the opposite best price,
within the position cap, and drop the resting order on the side we take.  python replay_take.py <live agent.py> <take agent.py>"""
import argparse, glob, json, sys, tempfile, importlib.util
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.protocol import MarketSimulationStateUpdate
bodies = [open(p).read() for p in sorted(glob.glob("/opt/mvtrx/cap/req_*.json"))]


def run(path, force=None, **kw):
    spec = importlib.util.spec_from_file_location("QA" + str(abs(hash((path, force)))), path); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    cfg = argparse.Namespace(size=0.06, skew=6.0, max_inv=0.3, edge=1, model="/opt/mvtrx/agents/model30_of.json", alpha_k=1.0, join=1, pull=1.0,
                             max_units=40, lazy_load=1, lean=1, raw=1, cancel_first=1, flow_pull=0.3, flow_win=10, flow_cool=3,
                             tape=tempfile.mktemp(), data_dir=tempfile.mkdtemp(), **kw)
    a = mod.QuoteAgent(93, cfg, tempfile.mkdtemp())
    if force is not None:
        a._predict = lambda book_id, book, sec, mid: force * 0.01
    out = []
    for b in bodies:
        syn = MarketSimulationStateUpdate(**json.loads(b)); syn.decompress(lazy=True)
        out.append(sorted(json.dumps(i.model_dump(), sort_keys=True, default=str) for i in a.handle(syn).instructions))
    return out


live, off = run(sys.argv[1]), run(sys.argv[2], take=0.0)
print("take=0 identical to live:", live == off, "| instructions", sum(map(len, live)))
for f in (5.0, -5.0):
    on = run(sys.argv[2], force=f, take=4.0, take_size=10.0, take_cool=30)
    ioc = [json.loads(x) for st in on for x in st if '"timeInForce": 2' in x or "IOC" in x]
    sides = {i.get("direction") for i in ioc}; qs = [i.get("quantity") for i in ioc]
    print(f"forced pred {f:+} ticks: instructions {sum(map(len, on))}, IOC takes {len(ioc)} on {len({i.get('bookId') for i in ioc})} books, directions {sides}, "
          f"qty max {max(qs) if qs else None}")
    if ioc:
        print("   sample:", {k: ioc[0].get(k) for k in ("bookId", "direction", "price", "quantity", "timeInForce", "postOnly", "stp")})
