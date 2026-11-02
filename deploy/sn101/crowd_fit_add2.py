"""SN101 crowd-fit lab, step 4 (droplet; decisions.md §1211 addendum): selection rules on top of the verbatim recipe, drawn apart from the
crowd. Raw draws are stored ("draws_verb5": 5 × verbatim gpt-4o-mini, "verb6": one 6-phrase answer); the lab box embeds and selects.

    /opt/tag101/venv/bin/python crowd_fit_add2.py
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/opt/tag101")
import crowd_fit_gen as G  # noqa: E402


def chat_n(system, post, model, n):
    """Like crowd_fit_gen.chat but keeps up to n tags."""
    import urllib.request
    body = {"model": model, "messages": [{"role": "system", "content": system.format(n=n)}, {"role": "user", "content": G.REF_USER.format(post=post)}]}
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {G.KEY}"})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                text = json.loads(r.read())["choices"][0]["message"]["content"].strip().strip("`").removeprefix("json").strip()
            tags = json.loads(text)
            if isinstance(tags, list):
                return [str(t) for t in tags][:n]
        except Exception:
            continue
    return []


def main():
    recs = [json.loads(l) for l in open("/opt/tag101/crowd_fit_cands.jsonl")]
    with open("/opt/tag101/crowd_fit_cands2.jsonl", "w") as f, ThreadPoolExecutor(12) as ex:
        for i, r in enumerate(recs):
            jobs = [3] * 5 + [6]
            res = list(ex.map(lambda n: chat_n(G.VERBATIM, r["post"], "gpt-4o-mini", n), jobs))
            r["draws_verb5"] = [x for x in res[:5] if x]; r["verb6"] = res[5]
            f.write(json.dumps(r) + "\n")
            print(f"{i + 1}/{len(recs)}", flush=True)


if __name__ == "__main__":
    main()
