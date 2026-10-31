"""CliqueAI diversity (decisions.md §1195): the validator pays 1 / (miners returning the identical clique), and the field returns distinct
maximum cliques (≈ 70 distinct best answers among 72 responders on a typical problem). Our solvers converge on the same natural clique as
other common solvers, so we random-walk across equal-size cliques before answering: swap one member for an outside vertex adjacent to all
the others (same size, still a clique), then re-check maximality; the walk ends somewhere few others will be.
"""

from __future__ import annotations

import random


def plateau_walk(adj: list[set[int]], clique: list[int], steps: int, rng: random.Random) -> list[int]:
    cur = set(clique)
    n = len(adj)
    for _ in range(steps):
        out = rng.choice(tuple(cur))
        rest = cur - {out}
        cands = [u for u in range(n) if u not in cur and rest <= adj[u]]
        if cands:
            cur = rest | {rng.choice(cands)}
    grow = [u for u in range(n) if u not in cur and cur <= adj[u]]
    while grow:                                          # a swap can open room for an extra vertex: take it (bigger and still valid)
        cur.add(rng.choice(grow))
        grow = [u for u in range(n) if u not in cur and cur <= adj[u]]
    return sorted(cur)
