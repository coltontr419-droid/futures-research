"""Replay captured live states through QuoteAgent: lazy_load 0/1 × lean 0/1. Checks the orders are identical and times decompress + handle."""
import argparse, glob, json, sys, tempfile, time, importlib.util
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.protocol import MarketSimulationStateUpdate
spec = importlib.util.spec_from_file_location("QuoteAgent", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
bodies = [open(p).read() for p in sorted(glob.glob("/opt/mvtrx/cap/req_*.json"))]
out = {}
tapes = {}
for lazy, lean, raw in ((0, 0, 0), (0, 1, 0), (1, 1, 1)):   # lazy without raw breaks: its cancel events have no side (§1207)
        tape = tempfile.mktemp(); tapes[(lazy, lean, raw)] = tape
        cfg = argparse.Namespace(size=0.01, skew=6.0, max_inv=0.05, edge=1, model="/opt/mvtrx/agents/model30_of.json", alpha_k=1.0, join=1,
                                 pull=1.0, max_units=20, lazy_load=lazy, lean=lean, raw=raw, tape=tape, data_dir=tempfile.mkdtemp())
        agent = mod.QuoteAgent(93, cfg, tempfile.mkdtemp())
        dec, han = [], []; instr = []
        for rep in range(6):                      # second pass: warm (books / mids already seen)
            for b in bodies:
                syn = MarketSimulationStateUpdate(**json.loads(b))
                t0 = time.perf_counter(); syn.decompress(lazy=bool(lazy)); t1 = time.perf_counter()
                r = agent.handle(syn); t2 = time.perf_counter()
                if rep >= 1:
                    dec.append(t1 - t0); han.append(t2 - t1)
                if rep <= 1:
                    instr.append(sorted(json.dumps(i.model_dump(), sort_keys=True, default=str) for i in r.instructions))
        med = lambda v: sorted(v)[len(v) // 2]; tot = [a + b for a, b in zip(dec, han)]; out[(lazy, lean, raw)] = instr
        print(f"lazy={lazy} lean={lean} raw={raw}: median decompress {med(dec):.3f} s, handle {med(han):.3f} s, total {med(tot):.3f} s per state (15 runs); {sum(map(len, instr))} instructions")
base = out[(0, 0, 0)]; base_tape = open(tapes[(0, 0, 0)]).read()
for k, v in out.items():
    same = all(len(a) == len(b) for a, b in zip(base, v))
    exact = v == base
    print(k, "same instruction counts" if same else "DIFFERENT counts", "| identical" if exact else "| contents differ", "| tape identical" if open(tapes[k]).read() == base_tape else "| TAPE DIFFERS")
