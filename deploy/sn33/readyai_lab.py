"""SN33 (ReadyAI) scoring lab (decisions.md §1185). Runs on the droplet with the user's OpenAI key.

Stand-in validator: GPT-4o tags each FULL conversation (first 150 lines of a ReadyAI podcast transcript) with the subnet's tagging prompt; the tags'
text-embedding-3-large vectors are averaged into the "neighbourhood". Miners see 10-line windows (2-line overlap, as the validator cuts them). Each
strategy's tags are scored with the evaluator's exact formula (cosine to the neighbourhood; 0.55 top-3 unique + 0.25 mean + 0.10 median + 0.10 max;
the no-match / few-unique / junk / few-tag penalties). The LLM keyword filter and the >20-tag random sample are not modelled (we submit <= 20 clean tags).

    /opt/tag101/venv/bin/python readyai_lab.py [n_conversations] [windows_per_conversation]
"""

from __future__ import annotations

import ast
import json
import random
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pyarrow.parquet as pq

KEY = [ln.split("=", 1)[1].strip() for ln in open("/opt/tag101/openai.env") if ln.startswith("OPENAI_API_KEY=")][0]
PROMPT = ("Analyze conversation in terms of topic interests of the participants. Analyze the conversation (provided in structured XML format) where <p0> has "
          "the questions and <p1> has the answers. Return comma-delimited tags. Only return the tags without any English commentary.")
CANDIDATES = ("Analyze conversation in terms of topic interests of the participants. Analyze the conversation (provided in structured XML format) where <p0> has "
              "the questions and <p1> has the answers. Return 25 comma-delimited lower-case tags: the specific topics and entities discussed, and also the broader "
              "themes the whole conversation is likely about. Only return the tags without any English commentary.")
BROAD = ("Analyze conversation in terms of topic interests of the participants. Analyze the conversation (provided in structured XML format) where <p0> has the "
         "questions and <p1> has the answers. Return 12 comma-delimited lower-case tags: mostly the broad, central themes of the conversation as a whole, plus "
         "a few specific topics. Only return the tags without any English commentary.")
FACTORS = {"top_3_mean": 0.55, "median_score": 0.1, "mean_score": 0.25, "max_score": 0.1}


def chat(prompt: str, text: str, model: str) -> list[str]:
    body = {"model": model, "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": text}]}
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        out = json.load(urllib.request.urlopen(req, timeout=120))["choices"][0]["message"]["content"]
    except Exception:
        return []
    return clean(out.split(","))


def clean(tags) -> list[str]:
    out = []
    for t in tags:
        t = re.sub(r"\s+", " ", str(t).strip().strip(".").lower())
        if t and len(t) <= 50 and t not in out:
            out.append(t)
    return out


def embed(tags: list[str]) -> dict[str, np.ndarray]:
    out = {}
    for i in range(0, len(tags), 200):
        chunk = tags[i:i + 200]
        req = urllib.request.Request("https://api.openai.com/v1/embeddings", json.dumps({"model": "text-embedding-3-large", "input": chunk}).encode(),
                                     {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
        for t, d in zip(chunk, json.load(urllib.request.urlopen(req, timeout=120))["data"]):
            out[t] = np.array(d["embedding"])
    return out


def score(gt: list[str], centre: np.ndarray, tags: list[str], vec: dict) -> float:
    """The evaluator's formula (validator/evaluator.py), our copy."""
    tags = list(dict.fromkeys(tags))
    if len(tags) < 3:
        return 0.0
    both, unique = set(gt) & set(tags), [t for t in tags if t not in set(gt)]
    cos = lambda v: float(np.dot(centre, v) / (np.linalg.norm(centre) * np.linalg.norm(v)))
    s = [cos(vec[t]) for t in tags[:21]]
    su = sorted(cos(vec[t]) for t in unique[:21]) or [0.0, 0.0, 0.0]
    top3 = (su[-3:] + [0.0, 0.0, 0.0])[:3] if len(su) < 3 else su[-3:]
    adj = FACTORS["top_3_mean"] * np.mean(top3) + FACTORS["median_score"] * np.median(s) + FACTORS["mean_score"] * np.mean(s) + FACTORS["max_score"] * max(s)
    if not both:
        adj *= 0.9
    if max(s) < 0.2:
        adj *= 0.5
    if len(tags) < 2:
        adj *= 0.2
    n_u = len(unique)
    adj *= 0.85 if n_u < 1 else 0.9 if n_u < 2 else 0.95 if n_u < 3 else 1.0
    return float(adj)


def lines_of(row) -> list[str]:
    tr = row["transcript"]; tr = ast.literal_eval(tr) if isinstance(tr, str) else tr; spk = {}
    out = []
    for x in tr:
        p = spk.setdefault(x.get("speaker"), len(spk) % 2)
        out.append(f"<p{p}>{x.get('text', '').strip()}</p{p}>")
    return out


def windows(lines: list[str], size=10, overlap=2) -> list[list[str]]:
    return [lines[i:i + size] for i in range(0, max(len(lines) - overlap, 1), size - overlap) if len(lines[i:i + size]) >= 4]


def central(cands: list[str], vec: dict, k: int) -> list[str]:
    if not cands:
        return []
    c = np.mean([vec[t] for t in cands], axis=0)
    return sorted(cands, key=lambda t: -float(np.dot(c, vec[t]) / (np.linalg.norm(c) * np.linalg.norm(vec[t]))))[:k]


def main(n: int, per: int) -> None:
    rows = pq.read_table("/opt/readyai_lab/convs.parquet").to_pylist(); rng = random.Random(1185); rng.shuffle(rows)
    res = {}
    for ci, row in enumerate(rows[:n]):
        lines = lines_of(row)[:150]
        if len(lines) < 30:
            continue
        gt = chat(PROMPT, "\n".join(lines), "gpt-4o")
        if len(gt) < 3:
            continue
        wins = rng.sample(windows(lines), min(per, len(windows(lines))))
        jobs = []
        for w in wins:
            t = "\n".join(w)
            jobs += [("default_4o", PROMPT, t, "gpt-4o"), ("default_mini", PROMPT, t, "gpt-4o-mini"), ("cands", CANDIDATES, t, "gpt-4o-mini"),
                     ("broad_mini", BROAD, t, "gpt-4o-mini")]
        with ThreadPoolExecutor(8) as ex:
            outs = list(ex.map(lambda j: chat(j[1], j[2], j[3]), jobs))
        allt = list(dict.fromkeys(gt + [t for o in outs for t in o])); vec = embed(allt)
        centre = np.mean([vec[t] for t in gt], axis=0)
        for wi in range(len(wins)):
            o = dict(zip(["default_4o", "default_mini", "cands", "broad_mini"], outs[wi * 4:wi * 4 + 4]))
            strategies = {"default_4o": o["default_4o"], "default_mini": o["default_mini"], "broad_mini": o["broad_mini"][:20],
                          "central5": central(o["cands"], vec, 5), "central10": central(o["cands"], vec, 10), "central15": central(o["cands"], vec, 15),
                          "cands_all20": o["cands"][:20]}
            for name, tags in strategies.items():
                if tags:
                    res.setdefault(name, []).append(score(gt, centre, tags, vec))
        print(f"conversation {ci + 1}/{n}: {len(wins)} windows, ground-truth tags {len(gt)}", flush=True)
    print(f"\n{'strategy':14} {'windows':>7} {'mean score':>10} {'vs default_4o':>14} {'weight (cubed) vs default_4o':>30}")
    base = np.mean(res.get("default_4o", [1]))
    for name in sorted(res, key=lambda k: -np.mean(res[k])):
        m = np.mean(res[name]); print(f"{name:14} {len(res[name]):7} {m:10.4f} {(m / base - 1) * 100:+13.1f}% {((m / base) ** 3 - 1) * 100:+29.1f}%")
    json.dump({k: list(map(float, v)) for k, v in res.items()}, open("/opt/readyai_lab/lab_results.json", "w"))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20, int(sys.argv[2]) if len(sys.argv) > 2 else 2)
