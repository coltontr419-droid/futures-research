"""CliqueAI (SN83) benchmark problems from the validator's public W&B history (parquet chunks in data/clique). decisions.md §1165.

    python -m futuresres.synth.clique_data      # converts data/clique/h_*.parquet -> data/clique/p/<step>.json (edge list + answer summary)
"""

from __future__ import annotations

import ast
import gc
import glob
import json
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "data" / "clique"
OUT = DIR / "p"


def convert() -> None:
    import pyarrow.parquet as pq
    OUT.mkdir(exist_ok=True)
    for f in sorted(glob.glob(str(DIR / "h_*.parquet"))):
        pf = pq.ParquetFile(f)
        for batch in pf.iter_batches(batch_size=5, columns=["_step", "number_of_nodes", "time_limit", "difficulty", "adjacency_list", "miner_ans"]):
            for r in batch.to_pylist():
                o = OUT / f"{int(r['_step'])}.json"
                if o.exists() or r["adjacency_list"] is None:
                    continue
                try:
                    lit = lambda v: ast.literal_eval(v) if isinstance(v, str) else v
                    adj = lit(r["adjacency_list"]); ans = lit(r["miner_ans"])
                except Exception:
                    continue
                sizes = [len(a) for a in ans]; best = max(sizes) if sizes else 0
                bestsets = sorted({tuple(sorted(int(x) for x in a)) for a in ans if len(a) == best})
                o.write_text(json.dumps({"n": int(r["number_of_nodes"]), "t": float(r["time_limit"]), "d": r["difficulty"],
                                         "adj": [[int(x) for x in row] for row in adj], "sizes": sizes, "best": best, "best_sets": bestsets[:5]}))
                del adj, ans
            gc.collect()


def summary() -> None:
    P = []
    for f in OUT.glob("*.json"):                              # one at a time: keep the stats, drop the graph
        p = json.loads(f.read_text()); p["dens"] = sum(len(a) for a in p["adj"]) / (p["n"] * (p["n"] - 1)); del p["adj"]; P.append(p)
    print(len(P), "problems")
    for lo, hi in ((0, 400), (400, 600), (600, 800), (800, 1000)):
        Q = [p for p in P if lo <= p["n"] < hi]
        if not Q:
            continue
        dens = [p["dens"] for p in Q]
        at = [sum(1 for s in p["sizes"] if s == p["best"]) / max(len(p["sizes"]), 1) for p in Q]
        print(f"n {lo}-{hi}: {len(Q)} problems, density median {st.median(dens):.3f} (min {min(dens):.3f} max {max(dens):.3f}), best clique median {st.median(p['best'] for p in Q)}, "
              f"miners at best: median {st.median(at):.2f}, problems with < 50% at best: {sum(a < 0.5 for a in at)}")


if __name__ == "__main__":
    convert(); summary()
