"""SN101 scoring lab, step 2 (runs on the laptop with the validator's own TagScorer): score each candidate strategy as one extra miner inside a stand-in
crowd of ~220 miners per post, built from the generated answers (stock-prompt answers drawn most often, so their real duplication rate carries over).
decisions.md §1177. Input: lab_crowd.jsonl copied from the droplet.

    ~/sn101lab/venv/bin/python lab_score.py lab_crowd.jsonl
"""

from __future__ import annotations

import json
import random
import sys
import time

import numpy as np

from tag101.tasks.sn101 import REFERENCE_MODEL_NAME, SN101_MAX_TAGS
from tag101.tasks.sn101_reference.core.scoring import TagScorer

MIX = {"crowd_ref": 75, "crowd_ent": 12, "crowd_space": 12, "crowd_41": 10}       # assumed field (half-size): mostly stock-prompt miners
SCALE = sum(MIX.values()) / 220.0                                                # repeated-set threshold scaled to the half-size crowd


def crowd_for(rec: dict, rng: random.Random) -> list[list[str]]:
    by = {}
    for c in rec["crowd"]:
        by.setdefault(c["kind"], []).append(c["tags"])
    out = []
    for kind, n in MIX.items():
        pool = by.get(kind) or by.get("crowd_ref", [])
        out += [list(rng.choice(pool)) for _ in range(n)] if pool else []
    return out


def main(path: str) -> None:
    import tag101.tasks.sn101_reference.core.scoring.tag_scorer as ts
    from tag101.tasks.sn101_reference.core.scoring import preprocessing as pp
    base = pp.repeated_set_adjustment
    ts.repeated_set_adjustment = lambda count, **kw: base(count, c=50.0 * SCALE)
    scorer = TagScorer(model_name=REFERENCE_MODEL_NAME, n_tags_per_miner=SN101_MAX_TAGS)
    recs = [json.loads(l) for l in open(path)]
    rel = {}; raw = {}
    for i, rec in enumerate(recs):
        rng = random.Random(1177 + i); crowd = crowd_for(rec, rng)
        if len(crowd) < 50:
            continue
        names = [n for n, t in rec["candidates"].items() if t]          # all candidates in one pass: 7 extra miners barely move a crowd of ~220
        t0 = time.time()
        s = scorer.score(rec["post"], crowd + [rec["candidates"][n] for n in names]).get("miner_scores", [])
        if len(s) < len(crowd) + len(names):
            continue
        med = float(np.median(s[:len(crowd)]))
        for j, name in enumerate(names):
            ours = s[len(crowd) + j]
            raw.setdefault(name, []).append(ours)
            rel.setdefault(name, []).append(ours / med if med > 0 else np.nan)
        print(f"post {i + 1}/{len(recs)} scored in {time.time() - t0:.0f}s", flush=True)
    print(f"\n{'strategy':18} {'posts':>5} {'mean score':>10} {'vs crowd median':>16}")
    for name in sorted(rel, key=lambda n: -np.nanmean(rel[n])):
        print(f"{name:18} {len(rel[name]):5} {np.mean(raw[name]):10.4f} {np.nanmean(rel[name]) * 100:15.0f}%")


if __name__ == "__main__":
    main(sys.argv[1])
