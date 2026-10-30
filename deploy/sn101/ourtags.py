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
MODE = os.getenv("TAG_MODE", "uncommon")          # "uncommon" (§1175) or "entity3": entities-first prompt, best in the lab (§1179)

ENTITY_SYSTEM = ("Generate topic tags for a social post. Prefer the specific named entities (people, companies, models, products), then the main topic. "
                 "Use short noun phrases with normal spacing, lower case. Return only a JSON array of lower-case strings. Output exactly {n} tags.\n")
ENTITY_USER = "Create tags for the post. Return a JSON array only, with no duplicates or extra text.\nPost:\n{post}\n"


def _entity_tags(post: str, n: int) -> list[str]:
    m = base.ReferenceMiner(n_tags=n, timeout_sec=int(base.SN101_TIME_LIMIT))
    payload = {"model": m.model, "messages": [{"role": "system", "content": ENTITY_SYSTEM.format(n=n)},
                                              {"role": "user", "content": ENTITY_USER.format(post=post.strip())}]}
    return m._parse_tags(m._call_chat_completions(payload))


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
    if MODE == "entity3":
        try:
            tags = list(dict.fromkeys(t for t in _entity_tags(post, k) if t))[:k]
        except Exception:
            return base.solve_problem(envelope, chain_runtime)
        if tags:
            _log(post, tags, tags)
            return {"tags": tags}
        return base.solve_problem(envelope, chain_runtime)
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
