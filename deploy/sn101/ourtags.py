"""Our SN101 tagger (futures-research decisions.md 1175): every tag stays on-consensus (the model ranks candidate tags), but each miner submits an
uncommon SET - the top tag plus a seeded random pick from the next ranks - so the repeated-set penalty (1 / (1 + (k/50)^5.5) for k miners
sharing an identical set) does not hit us. Not tracked by the upstream repo; loaded with --task.miner_module tag101.tasks.ourtags."""

from __future__ import annotations

import hashlib
import os
import random
import re
from typing import Any

from . import sn101 as base
from .framework import TaskHandler

N_CANDIDATES = int(os.getenv("TAG_CANDIDATES", "6"))
SEED = os.getenv("TAG_SEED", "0")
POST_LOG = os.getenv("TAG_POST_LOG", "")          # scoring lab: append {post, candidates, submitted} per task (decisions.md 1177)
MODE = os.getenv("TAG_MODE", "uncommon")          # "uncommon" (§1175), "entity3": entities-first prompt (§1179), "extract": literal spans (§1191)

ENTITY_SYSTEM = ("Generate topic tags for a social post. Prefer the specific named entities (people, companies, models, products), then the main topic. "
                 "Use short noun phrases with normal spacing, lower case. Return only a JSON array of lower-case strings. Output exactly {n} tags.\n")
ENTITY_USER = "Create tags for the post. Return a JSON array only, with no duplicates or extra text.\nPost:\n{post}\n"


def _entity_tags(post: str, n: int) -> list[str]:
    m = base.ReferenceMiner(n_tags=n, timeout_sec=int(base.SN101_TIME_LIMIT))
    payload = {"model": m.model, "messages": [{"role": "system", "content": ENTITY_SYSTEM.format(n=n)},
                                              {"role": "user", "content": ENTITY_USER.format(post=post.strip())}]}
    return m._parse_tags(m._call_chat_completions(payload))


ENT_LABELS = ("PERSON", "ORG", "PRODUCT", "GPE", "WORK_OF_ART", "EVENT", "NORP", "LOC", "FAC", "LAW")
GENERIC = {"things", "thing", "years", "year", "people", "time", "today", "way", "lot", "information", "stuff", "day", "days", "week", "everyone"}
_nlp = None


def _extract_tags(post: str, n: int) -> list[str]:
    """Literal spans of the post: named entities first (in order of appearance), then noun chunks without leading determiners/pronouns."""
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("en_core_web_sm", disable=["lemmatizer"])
    text = re.sub(r"^RT @\w+:\s*", "", post)
    text = re.sub(r"https?://\S+", " ", text).replace("&amp;", "&")
    text = re.sub(r"[@#](\w+)", r"\1", text)
    doc = _nlp(text)
    out: list[str] = []

    def add(span) -> None:
        toks = [t for t in span if not (t.is_stop or t.is_punct or t.pos_ in ("DET", "PRON"))] if len(span) > 1 else list(span)
        while toks and (toks[0].is_stop or toks[0].pos_ in ("DET", "PRON", "ADP", "CCONJ") or toks[0].is_punct):
            toks = toks[1:]
        tag = re.sub(r"\s+", " ", " ".join(t.text for t in toks)).strip(" .,:;!?'\"…").lower()
        if tag in GENERIC or (len(toks) == 1 and toks[0].ent_type_ in ("DATE", "TIME", "CARDINAL")):
            return
        if 2 <= len(tag) <= 40 and any(c.isalpha() for c in tag) and tag not in out and not any(tag in o or o in tag for o in out):
            out.append(tag)

    for e in doc.ents:
        if e.label_ in ENT_LABELS:
            add(e)
    for c in sorted(doc.noun_chunks, key=lambda c: (-any(t.pos_ == "PROPN" for t in c), -len(c))):
        if len(out) >= n:
            break
        if c.root.pos_ in ("NOUN", "PROPN"):
            add(c)
    return out[:n]


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
    if MODE == "extract":
        try:
            tags = _extract_tags(post, k)
        except Exception:
            tags = []
        if len(tags) >= k:
            _log(post, ["extract"], tags)
            return {"tags": tags}
    if MODE in ("entity3", "extract"):
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
