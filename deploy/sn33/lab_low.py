"""ReadyAI lab, round 2 (decisions.md §1193): the validator's real grader is gpt-5.2 (mainnet validators are locked to the in-code default),
not GPT-4o. Same windows/scoring as readyai_lab.py; ground truth = gpt-5.2 on the full conversation."""
import random, sys
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pyarrow.parquet as pq
sys.path.insert(0, "/opt/readyai_lab")
import readyai_lab as L
import json as _j, urllib.request as _u
def chat_low(prompt, text, model):
    body = {"model": model, "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": text}], "reasoning_effort": "low", "service_tier": "priority"}
    req = _u.Request("https://api.openai.com/v1/chat/completions", _j.dumps(body).encode(), {"Content-Type": "application/json", "Authorization": f"Bearer {L.KEY}"})
    try:
        return L.clean(_j.load(_u.urlopen(req, timeout=120))["choices"][0]["message"]["content"].split(","))
    except Exception:
        return []

def main(n, per):
    rows = pq.read_table("/opt/readyai_lab/convs.parquet").to_pylist(); rng = random.Random(1201); rng.shuffle(rows); res = {}
    for ci, row in enumerate(rows[:n]):
        lines = L.lines_of(row)[:150]
        if len(lines) < 30: continue
        gt = L.chat(L.PROMPT, "\n".join(lines), "gpt-5.2")
        if len(gt) < 3: print("gt failed", ci, flush=True); continue
        wins = rng.sample(L.windows(lines), min(per, len(L.windows(lines)))); jobs = []
        for w in wins:
            t = "\n".join(w)
            jobs += [("stock_52", L.PROMPT, t, "gpt-5.2"), ("stock_mini", L.PROMPT, t, "gpt-4o-mini"), ("cands_52", L.CANDIDATES, t, "gpt-5.2"), ("cands_low", L.CANDIDATES, t, "LOW")]
        with ThreadPoolExecutor(8) as ex: outs = list(ex.map(lambda j: chat_low(j[1], j[2], "gpt-5.2") if j[3] == "LOW" else L.chat(j[1], j[2], j[3]), jobs))
        vec = L.embed(list(dict.fromkeys(gt + [t for o in outs for t in o]))); centre = np.mean([vec[t] for t in gt], axis=0)
        for wi in range(len(wins)):
            o = dict(zip(["stock_52", "stock_mini", "cands_52", "cands_low"], outs[wi * 4:wi * 4 + 4]))
            for name, tags in {"stock_52": o["stock_52"][:20], "stock_mini": o["stock_mini"][:20], "central15_52": L.central(o["cands_52"], vec, 15),
                               "central15_low (fix)": L.central(o["cands_low"], vec, 15)}.items():
                if tags: res.setdefault(name, []).append(L.score(gt, centre, tags, vec))
        print(f"conversation {ci + 1}/{n}", flush=True)
    base = np.mean(res["central15_52"])
    for k in sorted(res, key=lambda k: -np.mean(res[k])):
        m = np.mean(res[k]); d = np.array(res[k]) - np.array(res["central15_52"][:len(res[k])])
        print(f"{k:22} n={len(res[k]):3} mean={m:.4f} vs central15_52 {100*(m/base-1):+6.1f}%  cubed {100*((m/base)**3-1):+6.1f}%  paired t={d.mean()/(d.std(ddof=1)/np.sqrt(len(d))+1e-12):.1f}")

if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]))
