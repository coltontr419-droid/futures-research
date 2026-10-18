"""A79 summary (decisions.md 692): what completing thin books would have earned across the sampler's sweeps."""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    ALL = [json.loads(x) for x in (ROOT / "reports" / "lip_sampler.jsonl").read_text().splitlines()]
    # two interleaved samples (the afternoon run kept going after the "shutdown"; the resumed run drew a new 500): split by ticker overlap
    a0 = {r["ticker"] for r in ALL[0]["rows"]}
    groups = {"A": [x for x in ALL if len(a0 & {r["ticker"] for r in x["rows"]}) > 0.5 * len(x["rows"])]}
    groups["B"] = [x for x in ALL if x not in groups["A"]]
    for g, S in groups.items():
        if S:
            print(f"== sample {g}"); one(S)
    return 0


def one(S) -> None:
    print(f"{len(S)} sweeps, {S[0]['time']} -> {S[-1]['time']}")
    e = np.array([s["earn_day"] for s in S]); c = np.array([s["collateral"] for s in S]); m = np.array([s["markets"] for s in S]); th = np.array([s["thin"] for s in S])
    print(f"per sweep: thin {th.mean():.0f} of {m.mean():.0f} markets; est. earnings ${e.mean():,.0f}/day (range {e.min():,.0f}-{e.max():,.0f}) on ${c.mean():,.0f} collateral")
    # persistence: a market thin in one sweep - thin in the next sweep it appears in?
    seen = collections.defaultdict(list)
    for i, s in enumerate(S):
        for r in s["rows"]:
            seen[r["ticker"]].append((i, r["thin"], r["earn_day"], r["reward_day"], r["ticker"].split("-")[0]))
    pairs = [(a[1], b[1]) for v in seen.values() for a, b in zip(v, v[1:]) if b[0] == a[0] + 1]
    tt = sum(1 for a, b in pairs if a and b); t_ = sum(1 for a, b in pairs if a)
    print(f"persistence: thin in one sweep -> thin in the next: {tt}/{t_} = {tt / max(t_, 1):.0%}")
    # concentration and series
    by = collections.Counter(); ms = collections.Counter()
    for s in S:
        for r in s["rows"]:
            by[r["ticker"].split("-")[0]] += r["earn_day"] / len(S); ms[r["ticker"]] += r["earn_day"] / len(S)
    tot = sum(ms.values()); top = ms.most_common(10)
    print(f"top 10 markets carry {sum(v for _, v in top) / tot:.0%} of the estimated earnings; top series:")
    for k, v in by.most_common(12):
        print(f"   {k:24} ${v:8,.0f}/day")
    # scale to all programmes
    n_all = 6700
    print(f"scaled to ~{n_all} programmes: ~${e.mean() / m.mean() * n_all:,.0f}/day gross on ~${c.mean() / m.mean() * n_all:,.0f} collateral "
          "(if nobody else did it and shares held - an upper bound)")


if __name__ == "__main__":
    sys.exit(main())
