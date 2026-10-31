"""CliqueAI multi-restart diversity benchmark (decisions.md §1195): R randomized restarts per problem, answer = the maximum clique found by
the fewest restarts (least "natural"), ties broken by seed. Budget = FRAC x time limit on 4 cores, run W at a time."""
import json, random, sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, "/opt/clique/src")
from futuresres.synth.clique_bench import solve
FRAC, R, W = float(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]); OUT = open(sys.argv[4], "w")
SOLVERS = ["/opt/clique/bin/numvc"] * 3 + ["/opt/clique/bin/dlsmc2"]
for f in sorted(Path("/opt/clique/p").glob("*.json"), key=lambda f: int(f.stem)):
    p = json.loads(f.read_text()); step = int(f.stem); adj = [set(a) for a in p["adj"]]
    secs = round(p["t"] * FRAC * 4 / R, 2)
    with ThreadPoolExecutor(W) as ex:
        res = list(ex.map(lambda i: solve(SOLVERS[i % len(SOLVERS)], p, secs, step * 100 + i), range(R)))
    cl = []
    for c in res:
        if c and all(b in adj[a] for i, a in enumerate(c) for b in c[i + 1:]):
            cur = set(c); grow = [u for u in range(p["n"]) if u not in cur and cur <= adj[u]]
            while grow:
                cur.add(grow[0]); grow = [u for u in range(p["n"]) if u not in cur and cur <= adj[u]]
            cl.append(tuple(sorted(cur)))
    if not cl:
        OUT.write(json.dumps({"step": step, "clique": [], "distinct": 0}) + "\n"); continue
    best = max(len(c) for c in cl); cnt = Counter(c for c in cl if len(c) == best)
    rng = random.Random(step); pick = min(cnt, key=lambda c: (cnt[c], rng.random()))
    OUT.write(json.dumps({"step": step, "clique": list(pick), "distinct": len(cnt), "restarts_at_best": sum(cnt.values())}) + "\n"); OUT.flush()
    print(step, p["n"], p["t"], "best", p["best"], "ours", best, "distinct", len(cnt), flush=True)
