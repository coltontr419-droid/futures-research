"""Benchmark a max-clique solver binary on the CliqueAI problems (data/clique/p): our clique size vs the field's best, at a fraction of each
problem's time limit. decisions.md §1165.

    python -m futuresres.synth.clique_bench <binary> <time_fraction> [limit] [pd]
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
P = ROOT / "data" / "clique" / "p"


def solve(binary: str, p: dict, secs: float, seed: int) -> list[int]:
    inp = f"{p['n']} {secs} {seed}\n" + "\n".join(f"{len(a)} " + " ".join(map(str, a)) for a in p["adj"]) + "\n"
    out = subprocess.run([binary], input=inp, capture_output=True, text=True, timeout=secs + 20).stdout.split("\n")
    return [int(x) for x in out[1].split()] if len(out) > 1 and out[1].strip() else []


def valid(p: dict, c: list[int]) -> bool:
    s = [set(a) for a in p["adj"]]
    return all(b in s[a] for i, a in enumerate(c) for b in c[i + 1:])


def main(binary: str, frac: float, limit: int = 10_000) -> None:
    files = sorted(P.glob("*.json")); random.Random(1165).shuffle(files); files = files[:limit]
    tally = {"win": 0, "tie": 0, "lose": 0, "invalid": 0}; hard = {"win": 0, "tie": 0, "lose": 0}; rows = []
    for f in files:
        p = json.loads(f.read_text()); c = solve(binary, p, round(p["t"] * frac, 2), int(f.stem))
        if not valid(p, c):
            tally["invalid"] += 1; continue
        k = "win" if len(c) > p["best"] else "tie" if len(c) == p["best"] else "lose"; tally[k] += 1
        at = sum(1 for s in p["sizes"] if s == p["best"]) / max(len(p["sizes"]), 1)
        if at < 0.5:
            hard[k] += 1
        rows.append((f.stem, p["n"], p["t"], p["best"], len(c), round(at, 2)))
    print("all:", tally, "| hard (< 50% of miners at the best):", hard)
    for r in [r for r in rows if r[4] < r[3]][:15]:
        print("  short:", r)


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 10_000)
