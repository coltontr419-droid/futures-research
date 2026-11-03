"""CliqueAI diversity by deletion (decisions.md §1213): start from our 8-restart answer B (multi_r8.jsonl); delete the d highest-degree
vertices of B (d = 1, 2, 3) and re-solve the reduced graph with NuMVC (3 seeds each, FRAC × time limit, in parallel); keep the new
maximum cliques (grown to maximal in the full graph) of B's size. Answer = one from the deepest deletion that still reaches the size
(seeded tie-break), else B. Written WITHOUT looking at the logged answers; cliques_del.jsonl is scored by clique_rank.py.
    python clique_delete.py <frac>   (from /opt/clique)"""
import json, random, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
FRAC = float(sys.argv[1]); BIN = "/opt/clique/bin/numvc"
base = {json.loads(l)["step"]: json.loads(l)["clique"] for l in open("multi_r8.jsonl")}
def numvc(n, adj, secs, seed):
    inp = f"{n} {secs} {seed}\n" + "\n".join(f"{len(a)} " + " ".join(map(str, a)) for a in adj) + "\n"
    try:
        out = subprocess.run([BIN], input=inp, capture_output=True, text=True, timeout=secs + 5).stdout.split("\n")
    except subprocess.TimeoutExpired:
        return []
    return [int(x) for x in out[1].split()] if len(out) > 1 and out[1].strip() else []
OUT = open("cliques_del.jsonl", "w"); stats = []
for f in sorted(Path("p").glob("*.json"), key=lambda f: int(f.stem)):
    p = json.loads(f.read_text()); step = int(f.stem); n = p["n"]; adj = [set(a) for a in p["adj"]]
    B = base.get(step) or []
    if not B:
        continue
    b = len(B); deg = sorted(B, key=lambda v: -len(adj[v])); secs = round(p["t"] * FRAC, 2)
    jobs = [(d, s) for d in (1, 2, 3) for s in range(3)]
    def run(job):
        d, s = job; gone = set(deg[:d]); keep = [v for v in range(n) if v not in gone]; idx = {v: i for i, v in enumerate(keep)}
        sub = [[idx[u] for u in adj[v] if u in idx] for v in keep]
        c = [keep[i] for i in numvc(len(keep), sub, secs, step * 1000 + d * 10 + s)]
        if not c or not all(y in adj[x] for i, x in enumerate(c) for y in c[i + 1:]):
            return d, None
        cur = set(c); grow = [u for u in range(n) if u not in cur and cur <= adj[u]]
        while grow:
            cur.add(grow[0]); grow = [u for u in range(n) if u not in cur and cur <= adj[u]]
        return d, tuple(sorted(cur))
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(run, jobs))
    good = [(d, c) for d, c in res if c and len(c) >= b and c != tuple(sorted(B))]
    if good:
        dmax = max(d for d, _ in good); pick = random.Random(step).choice(sorted({c for d, c in good if d == dmax}))
    else:
        dmax, pick = 0, tuple(sorted(B))
    OUT.write(json.dumps({"step": step, "clique": list(pick)}) + "\n"); OUT.flush()
    stats.append(dmax); print(step, n, p["t"], "base", b, "depth", dmax, "size", len(pick), flush=True)
print("depth reached:", {d: stats.count(d) for d in (0, 1, 2, 3)})
