"""SN101 scoring lab, step 1 (runs on the droplet, uses the user's OpenAI key): for each logged post, generate a stand-in crowd of miner answers and
our candidate strategies' answers. decisions.md §1177. Output: /opt/tag101/lab_crowd.jsonl (one line per post).

    /opt/tag101/venv/bin/python crowd.py [max_posts]
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

KEY = [ln.split("=", 1)[1].strip() for ln in open("/opt/tag101/openai.env") if ln.startswith("OPENAI_API_KEY=")][0]
POSTS = "/opt/tag101/posts.jsonl"
OUT = "/opt/tag101/lab_crowd.jsonl"

REF_SYSTEM = "Generate topic tags for a social post.\nReturn only a JSON array of lower-case strings.\nOutput exactly {n} tags.\n"
REF_USER = "Create tags for the post. Return a JSON array only, with no duplicates or extra text.\nPost:\n{post}\n"
ENT_SYSTEM = ("Generate topic tags for a social post. Prefer the specific named entities (people, companies, models, products), then the main topic. "
              "Use short noun phrases with normal spacing, lower case. Return only a JSON array of lower-case strings. Output exactly {n} tags.\n")
SPACE_SYSTEM = ("Generate topic tags for a social post. Each tag is a short lower-case noun phrase with normal spaces between words (for example "
                "\"peer review\", not \"peerreview\"). Return only a JSON array of lower-case strings. Output exactly {n} tags.\n")


def chat(system: str, user: str, model: str = "gpt-4o-mini", temperature: float | None = None) -> list[str]:
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if temperature is not None:
        body["temperature"] = temperature
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        text = json.load(urllib.request.urlopen(req, timeout=60))["choices"][0]["message"]["content"]
        m = re.search(r"\[.*\]", text, re.S)
        tags = json.loads(m.group(0)) if m else []
        return [str(t).strip().lower() for t in tags if str(t).strip()][:6]
    except Exception:
        return []


def uncommon(cands: list[str], post: str, seed: str, k: int = 3) -> list[str]:
    ranked = list(dict.fromkeys(cands))
    if len(ranked) <= k:
        return ranked
    rng = random.Random(hashlib.sha256(f"{seed}|{post}".encode()).digest())
    return [ranked[0]] + rng.sample(ranked[1:5], min(k - 1, len(ranked[1:5])))


def one(post: str) -> dict:
    u = REF_USER.format(post=post)
    jobs = ([("crowd_ref", REF_SYSTEM.format(n=3), "gpt-4o-mini")] * 25 + [("crowd_ent", ENT_SYSTEM.format(n=3), "gpt-4o-mini")] * 5 +
            [("crowd_space", SPACE_SYSTEM.format(n=3), "gpt-4o-mini")] * 5 + [("crowd_41", REF_SYSTEM.format(n=3), "gpt-4.1-mini")] * 5)
    with ThreadPoolExecutor(8) as ex:
        crowd = list(ex.map(lambda j: (j[0], chat(j[1], u, j[2])), jobs))
    six_ref = chat(REF_SYSTEM.format(n=6), u); six_ent = chat(ENT_SYSTEM.format(n=6), u); six_space = chat(SPACE_SYSTEM.format(n=6), u)
    cand = {"reference": chat(REF_SYSTEM.format(n=3), u), "uncommon_ref6": uncommon(six_ref, post, "lab"), "entity3": chat(ENT_SYSTEM.format(n=3), u),
            "uncommon_ent6": uncommon(six_ent, post, "lab"), "space3": chat(SPACE_SYSTEM.format(n=3), u), "uncommon_space6": uncommon(six_space, post, "lab"),
            "ref_41mini": chat(REF_SYSTEM.format(n=3), u, "gpt-4.1-mini")}
    return {"post": post, "crowd": [{"kind": k, "tags": t} for k, t in crowd if t], "candidates": cand}


def main(max_posts: int) -> None:
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)["post"] for l in open(OUT)}
    posts = list(dict.fromkeys(json.loads(l)["post"] for l in open(POSTS)))
    todo = [p for p in posts if p not in done and p.strip()][:max_posts]
    with open(OUT, "a") as f:
        for i, p in enumerate(todo):
            f.write(json.dumps(one(p)) + "\n"); f.flush()
            print(f"{i + 1}/{len(todo)}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 100)
