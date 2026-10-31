"""CliqueAI solver portfolio for the live miner (decisions.md §1195). R randomized restarts of our C solvers (NuMVC on the complement,
greedy+DLS-MC) across the box's cores inside the time budget; every result is grown to a maximal clique; returns the distinct
maximum-size cliques, least frequently found first (the least "natural" answers, least likely to coincide with other miners').

Binary I/O (src/futuresres/synth/numvc.c, dlsmc2.c): stdin "n secs seed" then one line per vertex "deg v1 v2 ..."; stdout line 2 = clique.
"""

from __future__ import annotations

import os
import random
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

BIN = os.getenv("CLIQUE_BIN", "/opt/clique/bin")
SOLVERS = ["numvc", "numvc", "numvc", "dlsmc2"]


def _run(binary: str, n: int, adj: list[list[int]], secs: float, seed: int) -> list[int]:
    inp = f"{n} {secs} {seed}\n" + "\n".join(f"{len(a)} " + " ".join(map(str, a)) for a in adj) + "\n"
    try:
        out = subprocess.run([binary], input=inp, capture_output=True, text=True, timeout=secs + 5).stdout.split("\n")
    except subprocess.TimeoutExpired:
        return []
    return [int(x) for x in out[1].split()] if len(out) > 1 and out[1].strip() else []


def _maximal(clique: list[int], sets: list[set[int]], n: int) -> tuple[int, ...] | None:
    if not clique or not all(b in sets[a] for i, a in enumerate(clique) for b in clique[i + 1:]):
        return None
    cur = set(clique)
    grow = [u for u in range(n) if u not in cur and cur <= sets[u]]
    while grow:
        cur.add(grow[0])
        grow = [u for u in range(n) if u not in cur and cur <= sets[u]]
    return tuple(sorted(cur))


def solve(n: int, adj: list[list[int]], budget: float, cores: int, restarts: int, seed: int) -> list[tuple[int, ...]]:
    """Distinct maximum cliques found within `budget` wall seconds on `cores` cores, least frequent first."""
    secs = max(0.5, round(budget * cores / restarts, 2))
    with ThreadPoolExecutor(cores) as ex:
        res = list(ex.map(lambda i: _run(os.path.join(BIN, SOLVERS[i % len(SOLVERS)]), n, adj, secs, seed * 100 + i), range(restarts)))
    sets = [set(a) for a in adj]
    found = [c for c in (_maximal(r, sets, n) for r in res) if c]
    if not found:
        return []
    best = max(len(c) for c in found)
    cnt = Counter(c for c in found if len(c) == best)
    rng = random.Random(seed)
    return sorted(cnt, key=lambda c: (cnt[c], rng.random()))
