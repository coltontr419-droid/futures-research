"""CliqueAI: where would our solver rank? (decisions.md §1195). For each logged problem, insert our benchmark clique size into the real
responder set and score it with the validator's formula (CliqueAI/scoring/clique_scoring.py): rel = size / max, pr = share of responders
strictly larger, optimality = exp(−pr/rel) / max, diversity = 1 / (identical answers) / max, reward = optimality·(1 + difficulty) + diversity.
Our clique is not stored, so diversity is bounded: high = our maximum clique differs from every logged answer (1), low = it equals the most
common logged answer of our size (1 / (k + 1)). Compared against every logged hotkey's mean reward over the same problems.

    python -m futuresres.synth.clique_rank <benchmark log | cliques.jsonl> <parquet>...

With a cliques.jsonl ({"step", "clique"} per line) our diversity is exact: 1 / (logged answers identical to ours + 1), and our clique is
checked against the graph's adjacency (a non-clique or extendable answer scores 0, as the validator's is_valid_maximum_clique does).
"""

from __future__ import annotations

import math
import statistics as st
import sys
from collections import Counter, defaultdict

import pyarrow.parquet as pq


def ours_by_step(log: str) -> dict[int, object]:
    out = {}
    if log.endswith(".jsonl"):
        import json
        for line in open(log):
            r = json.loads(line)
            out[int(r["step"])] = tuple(r["clique"])
        return out
    for line in open(log):
        f = line.split()
        if len(f) >= 8 and f[0].isdigit() and f[5] == "ours":
            out[int(f[0])] = int(f[6])
    return out


def main(log: str, files: list[str]) -> None:
    ours = ours_by_step(log)
    per_hk, ours_hi, ours_lo, n = defaultdict(list), [], [], 0
    for f in files:
        t = pq.read_table(f, columns=["_step", "difficulty", "miner_ans", "miner_hotkeys", "miner_rewards", "adjacency_list"]).to_pylist()
        for r in t:
            step = int(r["_step"])
            if step not in ours or not r["miner_ans"] or not r["miner_rewards"]:
                continue
            n += 1
            for hk, rw in zip(r["miner_hotkeys"], r["miner_rewards"]):
                per_hk[hk].append(rw)
            ans = [tuple(sorted(int(x) for x in a)) for a in r["miner_ans"]]
            mine = ours[step]
            if isinstance(mine, tuple):                     # exact clique: validate it as the validator does
                adj = [set(int(x) for x in row) for row in r["adjacency_list"]]
                ok = len(mine) > 0 and all(b in adj[a] for i, a in enumerate(mine) for b in mine[i + 1:])
                ok = ok and not any(set(mine) <= adj[v] for v in range(len(adj)) if v not in set(mine))
                me = len(mine) if ok else 0
            else:
                me = mine
            sizes = [len(a) for a in ans] + [me]
            best = max(sizes)
            rel = me / best; pr = sum(s > me for s in sizes) / len(sizes)
            opt = math.exp(-pr / rel)                       # the best responder's omega is exp(0) = 1, the normaliser
            d = float(r["difficulty"] or 0.0)
            if me == 0:
                ours_hi.append(0.0); ours_lo.append(0.0); continue
            if isinstance(mine, tuple):
                div = 1.0 / (Counter(ans)[mine] + 1)
                ours_hi.append(opt * (1 + d) + div); ours_lo.append(opt * (1 + d) + div)
                continue
            same = Counter(a for a in ans if len(a) == me)
            k = max(same.values()) if same else 0
            ours_hi.append(opt * (1 + d) + 1.0)
            ours_lo.append(opt * (1 + d) + 1.0 / (k + 1))
    regular = {hk: st.mean(v) for hk, v in per_hk.items() if len(v) >= max(5, n // 10)}
    field = sorted(regular.values())
    def pct(x):
        return 100 * sum(v < x for v in field) / len(field)
    print(f"problems {n}; hotkeys with >= {max(5, n // 10)} appearances: {len(field)}")
    print(f"field mean reward per problem: p10 {field[len(field) // 10]:.3f}  median {st.median(field):.3f}  p90 {field[9 * len(field) // 10]:.3f}  max {field[-1]:.3f}")
    print(f"ours (diversity high) {st.mean(ours_hi):.3f} → beats {pct(st.mean(ours_hi)):.0f}% of hotkeys")
    print(f"ours (diversity low)  {st.mean(ours_lo):.3f} → beats {pct(st.mean(ours_lo)):.0f}% of hotkeys")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
