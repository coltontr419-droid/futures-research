"""ReadyAI skill_generation lab (decisions.md §1211). The one task whose ground truth the miner can rebuild from its own input:
SkillGenerationTaskBundle._generate_metadata runs skill_to_metadata (gpt-5.2) on skill_markdown[:1000] with the task's input_categories, then
combine_metadata_tags(generateEmbeddings=True), and rewrites the miner's window to that same 1000-character markdown. Per logged task: one fresh
ground truth built that way (the validator's own draw is just another sample), then each answer variant goes through format_results'
validate_tag_set and the GroundTruthTagSimilarityScoringMechanism formula (lab_final.score) against it — all variants on the same ground truth.

  live          the logged answer (stock miner + scoring_fixes pre-clean)
  stock         a fresh stock answer (same distribution as live; checks the lab against the log)
  pool3 K       3 stock samples pooled, pre-cleaned, the K tags nearest the pool's centroid (K = 6, 10, 15, all)
  vote K        3 samples, tags ranked by how many samples gave them (ties: nearest the centroid), top K (K = 10, 15)

    cd /opt/readyai_lab && LLM_TYPE_OVERRIDE=openai OPENAI_MODEL=gpt-5.2 /opt/readyai/venv/bin/python lab_skillgen.py tasks_r3.jsonl,tasks_r3b.jsonl
"""
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import lab_final as LF  # noqa: E402  (sets the paths; score / vec_of)
from conversationgenome.llm.llm_factory import get_llm_backend  # noqa: E402
from conversationgenome.utils.Utils import Utils  # noqa: E402

llml = get_llm_backend()
safe = lambda tags: list(dict.fromkeys(t for t in (Utils.get_safe_tag(str(x)) for x in tags or []) if 3 <= len(t) <= 64))


def stock(md, cats):
    """SkillGenerationTask.mine: skill_to_metadata on the window, combine (no embeddings)."""
    r = llml.skill_to_metadata(md, generateEmbeddings=False, input_categories=cats)
    if not r or not r.tags:
        return []
    comb = llml.combine_metadata_tags([r.tags], generateEmbeddings=False)
    return comb.tags if comb else r.tags


def ground_truth(md, cats):
    r = llml.skill_to_metadata(md, input_categories=cats)
    if not r or not r.tags:
        return None, None
    res = llml.combine_metadata_tags([r.tags], generateEmbeddings=True)
    if not res or not res.success:
        return None, None
    return res.tags, np.mean([v["vectors"] for v in res.vectors.values()], axis=0)


def main(paths):
    rows = [json.loads(l) for p in paths.split(",") for l in open(f"/opt/readyai/{p}") if '"skill_generation"' in l]
    res = {}
    for k, r in enumerate(rows):
        md, cats = r["input"]["data"]["window"][0][1], r["input"].get("input_categories")
        with ThreadPoolExecutor(5) as ex:
            gt_f = ex.submit(ground_truth, md, cats); samples = list(ex.map(lambda _: stock(md, cats), range(4)))
            gt, centre = gt_f.result()
        if not gt:
            print(f"task {k + 1}: no ground truth", flush=True); continue
        fresh, pool_s = samples[0], samples[1:]
        pool = safe([t for s in pool_s for t in s])
        vec = LF.vec_of(llml, list(set(pool) | set(safe((r.get("output") or {}).get("tags"))) | set(safe(fresh))))
        pc = np.mean([vec[t] for t in pool if t in vec], axis=0) if pool else None
        cos = lambda t: float(pc @ vec[t] / (np.linalg.norm(pc) * np.linalg.norm(vec[t]))) if t in vec and pc is not None else -9
        near = sorted(pool, key=lambda t: -cos(t))
        votes = Counter(t for s in pool_s for t in set(safe(s)))
        voted = sorted(pool, key=lambda t: (-votes[t], -cos(t)))
        variants = {"live": (r.get("output") or {}).get("tags") or [], "stock": safe(fresh)}
        for K in (6, 10, 15):
            variants[f"pool3 nearest {K}"] = near[:K]
        variants["pool3 all"] = near
        for K in (10, 15):
            variants[f"vote {K}"] = voted[:K]
        line = []
        for name, tags in variants.items():
            scored = llml.validate_tag_set(tags) if tags else []
            missing = [t for t in scored or [] if t not in vec]
            if missing:
                vec.update(LF.vec_of(llml, missing))
            s = LF.score(gt, centre, scored or [], vec) if scored else 0.0
            res.setdefault(name, []).append(s); line.append(f"{name} {s:.3f}")
        res.setdefault("_exact", []).append(len(set(gt) & set(variants["live"])))
        print(f"task {k + 1}/{len(rows)}: gt {len(gt)} | " + " | ".join(line), flush=True)
    base = np.array(res["live"])
    for name in [n for n in res if not n.startswith("_")]:
        a = np.array(res[name]); d = a - base
        t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)) + 1e-12) if len(d) > 1 else 0
        print(f"{name:18} n={len(a)} mean {a.mean():.4f} ({100 * (a.mean() / base.mean() - 1):+.1f}% vs live, paired t {t:.1f}) zeros {np.mean(a == 0):.0%}")
    json.dump(res, open("/opt/readyai_lab/lab_skillgen.json", "w"))


if __name__ == "__main__":
    main(sys.argv[1])
