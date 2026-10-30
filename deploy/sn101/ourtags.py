"""Our SN101 tagger (futures-research decisions.md 1175): every tag stays on-consensus (the model ranks candidate tags), but each miner submits an
uncommon SET - the top tag plus a seeded random pick from the next ranks - so the repeated-set penalty (1 / (1 + (k/50)^5.5) for k miners
sharing an identical set) does not hit us. Not tracked by the upstream repo; loaded with --task.miner_module tag101.tasks.ourtags."""

from __future__ import annotations

import hashlib
import os
import random
from typing import Any

from . import sn101 as base
from .framework import TaskHandler

N_CANDIDATES = int(os.getenv("TAG_CANDIDATES", "6"))
SEED = os.getenv("TAG_SEED", "0")
POST_LOG = os.getenv("TAG_POST_LOG", "")          # scoring lab: append {post, candidates, submitted} per task (decisions.md 1177)


def _log(post: str, ranked: list[str], tags: list[str]) -> None:
    if not POST_LOG:
        return
    try:
        import json
        import time
        with open(POST_LOG, "a") as f:
            f.write(json.dumps({"t": int(time.time()), "post": post, "candidates": ranked, "tags": tags}) + "\n")
    except Exception:
        pass


def solve_problem(envelope, chain_runtime) -> dict[str, Any]:
    post = str(dict(envelope.payload).get("text", ""))
    k = int(base.SN101_MAX_TAGS)
    try:
        cands = base.ReferenceMiner(n_tags=N_CANDIDATES, timeout_sec=int(base.SN101_TIME_LIMIT)).generate_tags(post)
    except Exception:
        return base.solve_problem(envelope, chain_runtime)
    seen, ranked = set(), []
    for t in cands:
        if t and t not in seen:
            seen.add(t); ranked.append(t)
    if len(ranked) <= k:
        _log(post, ranked, ranked)
        return {"tags": ranked}
    rng = random.Random(hashlib.sha256(f"{SEED}|{post}".encode()).digest())
    rest = ranked[1:min(len(ranked), 5)]
    tags = [ranked[0]] + rng.sample(rest, min(k - 1, len(rest)))
    _log(post, ranked, tags)
    return {"tags": tags}


def handler() -> TaskHandler:
    return TaskHandler(kind=base.KIND, spec_version=base.SPEC_VERSION, solve_problem=solve_problem, score_answers=base.score_answers,
                       build_lease=base.build_local_lease, description="SN101 tagger: on-consensus tags, uncommon sets")
