"""CliqueAI: parallel portfolio benchmark (several seeds of NuMVC and greedy+DLS-MC on separate cores, best kept). decisions.md §1171.

    python -m futuresres.synth.clique_portfolio <time_fraction> [limit]
"""

from __future__ import annotations

import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from futuresres.synth.clique_bench import P, solve, valid

BIN = Path(__file__).resolve().parents[3] / "data" / "clique"
PORTFOLIO = [("numvc", s) for s in range(1, 7)] + [("dlsmc2", s) for s in range(1, 3)]


def best_of(p: dict, secs: float, seed0: int) -> list[int]:
    with ThreadPoolExecutor(len(PORTFOLIO)) as ex:
        res = list(ex.map(lambda bs: solve(str(BIN / bs[0]), p, secs, seed0 * 10 + bs[1]), PORTFOLIO))
    res = [c for c in res if valid(p, c)]
    return max(res, key=len) if res else []


def main(frac: float, limit: int = 60) -> None:
    files = sorted(P.glob("*.json")); random.Random(1165).shuffle(files); files = files[:limit]
    tally = {"win": 0, "tie": 0, "lose": 0}; short = []
    for f in files:
        p = json.loads(f.read_text()); c = best_of(p, round(p["t"] * frac, 2), int(f.stem))
        k = "win" if len(c) > p["best"] else "tie" if len(c) == p["best"] else "lose"; tally[k] += 1
        if k == "lose":
            short.append((f.stem, p["n"], p["t"], p["best"], len(c)))
    print("portfolio", tally); [print("  short:", s) for s in short]


if __name__ == "__main__":
    main(float(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 60)
