"""SN101 scoring lab, round 2 (droplet): re-use each post's stand-in crowd from lab_crowd.jsonl and generate variants of the round-1 winner
(entities-first prompt). decisions.md §1183. Output: /opt/tag101/lab_crowd2.jsonl (same records, new "candidates"), scored by lab_score.py.

    /opt/tag101/venv/bin/python crowd2.py
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

from crowd import ENT_SYSTEM, REF_USER, chat, uncommon

IN, OUT = "/opt/tag101/lab_crowd.jsonl", "/opt/tag101/lab_crowd2.jsonl"

STRUCT = ("Tag a social post. Tag 1: the most specific named entity in it (person, company, AI model, product, paper, place). Tag 2: another specific entity, "
          "or the specific technology or event. Tag 3: the broad topic. Short lower-case noun phrases with normal spacing. Return only a JSON array of exactly 3 strings.\n")
MIX = ("Tag a social post with exactly 3 tags: the single most important named entity, then the two main topics. Short lower-case noun phrases with normal "
       "spacing. Return only a JSON array of lower-case strings.\n")
CONCISE = ("Generate topic tags for a social post. Prefer the specific named entities (people, companies, models, products), then the main topic. Each tag is "
           "one or two words, lower case, normal spacing. Return only a JSON array of lower-case strings. Output exactly {n} tags.\n")


def variants(post: str) -> dict:
    u = REF_USER.format(post=post)
    jobs = {
        "entity3": (ENT_SYSTEM.format(n=3), "gpt-4o-mini", None),
        "entity3_t0": (ENT_SYSTEM.format(n=3), "gpt-4o-mini", 0.0),
        "ent_struct": (STRUCT, "gpt-4o-mini", None),
        "ent_mix": (MIX, "gpt-4o-mini", None),
        "ent_concise": (CONCISE.format(n=3), "gpt-4o-mini", None),
        "entity3_41": (ENT_SYSTEM.format(n=3), "gpt-4.1-mini", None),
        "ent6": (ENT_SYSTEM.format(n=6), "gpt-4o-mini", None),
    }
    with ThreadPoolExecutor(7) as ex:
        res = dict(zip(jobs, ex.map(lambda j: chat(j[0], u, j[1], j[2]), jobs.values())))
    six = res.pop("ent6")
    res["ent6_top3"] = list(dict.fromkeys(six))[:3]
    res["ent6_uncommon"] = uncommon(six, post, "lab2")
    return {k: v for k, v in res.items() if v}


def main() -> None:
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)["post"] for l in open(OUT)}
    recs = [json.loads(l) for l in open(IN)]
    with open(OUT, "a") as f:
        for i, r in enumerate(recs):
            if r["post"] in done:
                continue
            f.write(json.dumps({"post": r["post"], "crowd": r["crowd"], "candidates": variants(r["post"])}) + "\n"); f.flush()
            print(f"{i + 1}/{len(recs)}", flush=True)


if __name__ == "__main__":
    main()
