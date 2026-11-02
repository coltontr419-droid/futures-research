"""SN101 crowd-fit lab, step 1 (droplet; decisions.md §1211): candidate crowds. For a seeded sample of posts that m3 (modal), m4 (stock prompt on
gpt-5-mini) and m5 (extract) all answered live, each generator (model × prompt) answers K times; the stock / entity generators on gpt-4o-mini answer
once more for our own m2-era strategies (sample 0 = ours, never in the crowd). Step 2 (crowd_fit_score.py, lab box) scores our live answers
inside each candidate crowd with the validator's TagScorer and compares predicted gaps with the observed live ones.

    /opt/tag101/venv/bin/python crowd_fit_gen.py <n posts> <samples per generator>
"""
from __future__ import annotations

import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/opt/tag101")
from crowd import ENT_SYSTEM, REF_SYSTEM, REF_USER  # noqa: E402

KEY = [ln.split("=", 1)[1].strip() for ln in open("/opt/tag101/openai.env") if ln.startswith("OPENAI_API_KEY=")][0]
OUT = "/opt/tag101/crowd_fit.jsonl"

BROAD = ("Generate topic tags for a social post: the broad subject categories it belongs to (for example artificial intelligence, robotics, "
         "venture capital, neuroscience), not names. Return only a JSON array of lower-case strings.\nOutput exactly {n} tags.\n")
VERBATIM = ("Generate topic tags for a social post: the {n} most important key phrases, copied word for word from the post. Return only a JSON "
            "array of lower-case strings.\nOutput exactly {n} tags.\n")
KEYWORD = ("Generate topic tags for a social post. Each tag is a single word. Return only a JSON array of lower-case strings.\nOutput exactly {n} tags.\n")

GENS = {                                    # name: (system prompt, model)
    "ref_4omini": (REF_SYSTEM, "gpt-4o-mini"),
    "ref_41mini": (REF_SYSTEM, "gpt-4.1-mini"),
    "ref_41": (REF_SYSTEM, "gpt-4.1"),
    "ref_4o": (REF_SYSTEM, "gpt-4o"),
    "ref_5nano": (REF_SYSTEM, "gpt-5-nano"),
    "ref_5mini": (REF_SYSTEM, "gpt-5-mini"),
    "ent_4omini": (ENT_SYSTEM, "gpt-4o-mini"),
    "broad_4omini": (BROAD, "gpt-4o-mini"),
    "verbatim_4omini": (VERBATIM, "gpt-4o-mini"),
    "keyword_4omini": (KEYWORD, "gpt-4o-mini"),
}
OURS = {"ours_ref_4omini": "ref_4omini", "ours_ent_4omini": "ent_4omini"}   # m2's two live strategies, regenerated on these posts


def chat(system: str, post: str, model: str) -> list[str]:
    """The stock miner's request (no temperature, as players run it), its parser, then the validator-side shape: ≤ 3 strings."""
    import urllib.request
    body = {"model": model, "messages": [{"role": "system", "content": system.format(n=3)}, {"role": "user", "content": REF_USER.format(post=post)}]}
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                text = json.loads(r.read())["choices"][0]["message"]["content"].strip()
            if text.startswith("```"):
                text = "\n".join(x for x in text.splitlines() if not x.strip().startswith("```")).strip()
            tags = json.loads(text)
            if isinstance(tags, list):
                return [str(t) for t in tags][:3]
        except Exception:
            continue
    return []


def main(n: int, k: int) -> None:
    logs = {m: {} for m in ("m3", "m4", "m5")}
    for m in logs:
        for line in open(f"/opt/tag101/posts_{m}.jsonl"):
            r = json.loads(line)
            logs[m].setdefault(r["post"], r["tags"])
    posts = sorted(p for p in logs["m3"] if p in logs["m4"] and p in logs["m5"] and p.strip())
    random.Random(1211).shuffle(posts)
    done = {json.loads(l)["post"] for l in open(OUT)} if os.path.exists(OUT) else set()
    todo = [p for p in posts[:n] if p not in done]
    jobs = [(g, i) for g in GENS for i in range(k)] + [(o, 0) for o in OURS]
    with open(OUT, "a") as f, ThreadPoolExecutor(24) as ex:
        for j, post in enumerate(todo):
            res = list(ex.map(lambda gi: chat(GENS[OURS.get(gi[0], gi[0])][0], post, GENS[OURS.get(gi[0], gi[0])][1]), jobs))
            rec = {"post": post, "live": {m: logs[m][post] for m in logs}, "gens": {}, "ours": {}}
            for (g, _), tags in zip(jobs, res):
                if tags:
                    (rec["ours"].__setitem__(g, tags) if g in OURS else rec["gens"].setdefault(g, []).append(tags))
            f.write(json.dumps(rec) + "\n"); f.flush()
            print(f"{j + 1}/{len(todo)}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]))
