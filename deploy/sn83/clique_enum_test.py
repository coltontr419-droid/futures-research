"""CliqueAI diversity test (decisions.md §1213): for each logged problem, enumerate the maximum cliques (size = the best logged size) with
bin/enum_maxclique within FRAC × time_limit on one core, pick ours WITHOUT looking at the logged answers — 'random' (uniform over the
sample) and 'rare' (lowest Σ vertex frequency over all enumerated maximum cliques) — and write cliques_<rule>.jsonl for clique_rank.py.
    python clique_enum_test.py <frac> <parquet>...   (from /opt/clique)"""
import json, random, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
import pyarrow.parquet as pq
FRAC = float(sys.argv[1]); FILES = sys.argv[2:]
def solve(r):
    n = int(r["number_of_nodes"]); adj = [[int(x) for x in row] for row in r["adjacency_list"]]
    sizes = [len(a) for a in r["miner_ans"] if a]
    if not sizes: return None
    W = max(sizes); edges = [(u, v) for u in range(n) for v in adj[u] if u < v]
    inp = f"{n} {len(edges)} {W} 5000 {FRAC * float(r['time_limit']):.2f}\n" + "\n".join(f"{u} {v}" for u, v in edges) + "\n"
    out = subprocess.run(["bin/enum_maxclique"], input=inp, capture_output=True, text=True).stdout.split("\n")
    head = out[0].split(); count, complete, t = int(head[1]), int(head[3]), float(head[5])
    cl = [tuple(sorted(int(x) for x in l.split())) for l in out[1:] if l.strip() and not l.startswith("FREQ")]
    freq = [int(x) for x in [l for l in out if l.startswith("FREQ")][0].split()[1:]]
    logged = {tuple(sorted(int(x) for x in a)) for a in r["miner_ans"] if a and len(a) == W}
    if not cl: return dict(step=int(r["_step"]), n=n, W=W, count=0, complete=complete, t=t)
    rnd = random.Random(int(r["_step"])).choice(cl)
    rare = min(cl, key=lambda c: sum(freq[v] for v in c))
    return dict(step=int(r["_step"]), n=n, W=W, count=count, complete=complete, t=t, tl=float(r["time_limit"]), distinct_logged=len(logged),
                random=list(rnd), rare=list(rare), random_claimed=rnd in logged, rare_claimed=rare in logged)
rows = [row for f in FILES for b in pq.ParquetFile(f).iter_batches(batch_size=2, columns=["_step", "number_of_nodes", "adjacency_list", "miner_ans", "time_limit"]) for row in b.to_pylist()]
with ProcessPoolExecutor(3) as ex:
    res = [x for x in ex.map(solve, rows) if x]
json.dump(res, open("enum_results.json", "w"))
for rule in ("random", "rare"):
    with open(f"cliques_{rule}.jsonl", "w") as f:
        for x in res:
            if rule in x: f.write(json.dumps({"step": x["step"], "clique": x[rule]}) + "\n")
ok = [x for x in res if x["count"]]
print(f"problems {len(res)} | enumerated (≥1 max clique found in time) {len(ok)} | complete {sum(x['complete'] for x in res)} | "
      f"max cliques per problem median {sorted(x['count'] for x in ok)[len(ok)//2] if ok else 0} | distinct logged answers median {sorted(x['distinct_logged'] for x in ok)[len(ok)//2] if ok else 0}")
for rule in ("random", "rare"):
    print(f"{rule}: our pick already claimed by a logged answer on {sum(x[rule + '_claimed'] for x in ok)} of {len(ok)}")
