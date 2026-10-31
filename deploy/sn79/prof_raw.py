import argparse, glob, json, sys, tempfile, cProfile, pstats, importlib.util
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.protocol import MarketSimulationStateUpdate
spec = importlib.util.spec_from_file_location("QuoteAgent", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
bodies = [open(p).read() for p in sorted(glob.glob("/opt/mvtrx/cap/req_*.json"))]
cfg = argparse.Namespace(size=0.01, skew=6.0, max_inv=0.05, edge=1, model="/opt/mvtrx/agents/model30_of.json", alpha_k=1.0, join=1, pull=1.0,
                         max_units=20, lazy_load=1, lean=1, raw=1, tape=tempfile.mktemp(), data_dir=tempfile.mkdtemp())
agent = mod.QuoteAgent(93, cfg, tempfile.mkdtemp())
syns = []
for b in bodies:
    s = MarketSimulationStateUpdate(**json.loads(b)); s.decompress(lazy=True); syns.append(s)
pr = cProfile.Profile(); pr.enable()
for s in syns: agent.handle(s)
pr.disable(); pstats.Stats(pr).sort_stats("tottime").print_stats(14)
