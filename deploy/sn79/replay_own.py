"""Replay check for own_ex (§1211 addendum 6): own_ex=0 must reproduce the live agent's instructions exactly; own_ex=1 reports the share of
order / cancel events that were our own (by resting-order id) and how many instructions change.  python replay_own.py <live.py> <new.py>"""
import argparse, glob, json, sys, tempfile, importlib.util
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.protocol import MarketSimulationStateUpdate
bodies = [open(p).read() for p in sorted(glob.glob("/opt/mvtrx/cap/req_*.json"))]


def run(path, **kw):
    spec = importlib.util.spec_from_file_location("QA" + str(abs(hash((path, tuple(kw.items()))))), path); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    cfg = argparse.Namespace(size=0.06, skew=6.0, max_inv=0.3, edge=1, model="/opt/mvtrx/agents/model30_of.json", alpha_k=1.0, join=1, pull=1.0,
                             max_units=40, lazy_load=1, lean=1, raw=1, cancel_first=1, flow_pull=0.3, flow_win=10, flow_cool=3,
                             tape=tempfile.mktemp(), data_dir=tempfile.mkdtemp(), **kw)
    a = mod.QuoteAgent(93, cfg, tempfile.mkdtemp()); out = []
    for rep in range(2):
        for b in bodies:
            syn = MarketSimulationStateUpdate(**json.loads(b)); syn.decompress(lazy=True)
            out.append(sorted(json.dumps(i.model_dump(), sort_keys=True, default=str) for i in a.handle(syn).instructions))
    return out, a


live, _ = run(sys.argv[1]); off, _ = run(sys.argv[2], own_ex=0); on, a = run(sys.argv[2], own_ex=1)
print("own_ex=0 identical to live:", live == off, "| instructions", sum(map(len, live)))
sk, tot, sq, sqt = a.own_stats
print(f"own_ex=1: our share of order/cancel events {sk / max(tot, 1):.1%} by count, {sq / max(sqt, 1e-9):.1%} by size | own ids tracked {len(a._own)} | "
      f"states with changed instructions {sum(x != y for x, y in zip(live, on))} of {len(live)}")
