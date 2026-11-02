"""ReadyAI lab, round 4 (decisions.md §1210): score the FINAL conversation_tagging answer, enrichment included, against a ground truth built the
validator's way (ConversationTaggingTaskBundle._generate_metadata): stock conversation_to_metadata on the FULL conversation + enrichment_to_metadata
per enrichment line, merged by combine_metadata_tags, embedded with get_vector_embeddings_set; neighbourhood = mean of those vectors; scoring =
GroundTruthTagSimilarityScoringMechanism's formula (readyai_lab.score). Every LLM / embedding call is the repo's own LlmLib on gpt-5.2.
Enrichment search results are not available offline, so they are synthesized per conversation (2 queries × 3 results, title + snippet) and the
validator's sampling (1-3 per query) is applied. The miner side replays the live pipeline (central15 + parallel enrichment + combine) on 10-line
windows, then tests post-combine trims: keep the K tags nearest the centroid of the combined answer.

    LLM_TYPE_OVERRIDE=openai OPENAI_MODEL=gpt-5.2 python lab_final.py <n conversations> <windows per conversation>
"""
import ast
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, "/opt/readyai_lab")
sys.path.insert(0, "/opt/readyai")
sys.path.insert(0, "/opt/readyai/repo")
import types  # noqa: E402
sys.modules.setdefault("pyarrow", types.ModuleType("pyarrow")); sys.modules.setdefault("pyarrow.parquet", types.ModuleType("pyarrow.parquet"))  # readyai_lab imports it; unused here
import readyai_lab as L  # noqa: E402
import central15  # noqa: E402  (patches LlmLib.conversation_to_metadata; the stock one stays at central15._stock)
from conversationgenome.api.models.conversation import Conversation  # noqa: E402
from conversationgenome.llm.llm_factory import get_llm_backend  # noqa: E402
from conversationgenome.utils.Utils import Utils  # noqa: E402

SYNTH = ("You simulate a web search API. Read the conversation and write the 2 search queries a researcher would run about its main subjects, and "
         "for each query 3 realistic search results. Return only JSON: {\"query\": [{\"title\": ..., \"snippet\": ...}, ...], ...}; snippets 1-2 "
         "sentences, like a search engine shows.")


def lines_of(row):
    tr = row["transcript"]; tr = ast.literal_eval(tr) if isinstance(tr, str) else tr; spk = {}
    return [[spk.setdefault(x.get("speaker"), len(spk) % 2), x.get("text", "").strip()] for x in tr]


def enrichment_lines(llml, lines, rng):
    raw = llml.basic_prompt(SYNTH + "\n\n" + "\n".join(f"<p{p}>{t}</p{p}>" for p, t in lines[:150]))
    try:
        res = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except Exception:
        return []
    out = []
    for _, results in res.items():
        if not results:
            continue
        for r in rng.sample(results, rng.randint(1, min(3, len(results)))):          # the validator's sampling
            text = f"{r.get('title') or ''}\n{r.get('snippet') or ''}"[:1000]
            if text.strip():
                out.append((len(out), text))
    return out


def ground_truth(llml, lines, enr):
    meta = central15._stock(llml, Conversation(guid="lab", lines=lines, participants=["p0", "p1"]), generateEmbeddings=False)
    if not meta or not meta.success:
        return None, None
    all_tags = [meta.tags] + [m.tags for m in (llml.enrichment_to_metadata(t) for _, t in enr) if m and m.tags]
    res = llml.combine_metadata_tags(all_tags, generateEmbeddings=True) if len(all_tags) > 1 else None
    tags = res.tags if res and res.success else meta.tags
    vecs = res.vectors if res and res.success else llml.get_vector_embeddings_set(meta.tags)
    return tags, np.mean([v["vectors"] for v in vecs.values()], axis=0)


def miner_answer(llml, window, enr):
    """The live pipeline (central15._mine without the task wrapper)."""
    result = llml.conversation_to_metadata(conversation=Conversation(guid="lab", lines=window), generateEmbeddings=False)
    if not enr:
        return result.tags
    prev = central15._fast(llml)
    try:
        with ThreadPoolExecutor(min(8, len(enr))) as ex:
            outs = list(ex.map(lambda c: llml.enrichment_to_metadata(c, generateEmbeddings=False), [c for _, c in enr]))
        all_tags = ([result.tags] if result and result.tags else []) + [o.tags for o in outs if o and o.tags]
        combined = llml.combine_metadata_tags(all_tags, generateEmbeddings=False)
    finally:
        for k, v in prev.items():
            setattr(llml, k, v)
    return combined.tags if combined else result.tags


def vec_of(llml, tags):
    return {t: np.asarray(v["vectors"]) for t, v in llml.get_vector_embeddings_set(tags).items()}


def score(gt, centre, tags, vec):
    """GroundTruthTagSimilarityScoringMechanism (as readyai_lab.score), with a tag that has no vector scoring 0, as the validator does."""
    tags = list(dict.fromkeys(tags))
    if len(tags) < 3:
        return 0.0
    gts = set(gt); unique = [t for t in tags if t not in gts]
    cos = lambda t: float(centre @ vec[t] / (np.linalg.norm(centre) * np.linalg.norm(vec[t]))) if t in vec and np.linalg.norm(vec[t]) > 0 else 0.0
    sc = [cos(t) for t in tags[:21]]; su = sorted(cos(t) for t in unique[:21])
    top3 = (su[-3:] if len(su) >= 3 else su + [0.0] * (3 - len(su))) if su else [0.0, 0.0, 0.0]
    F = L.FACTORS
    adj = F["top_3_mean"] * np.mean(top3) + F["median_score"] * np.median(sc) + F["mean_score"] * np.mean(sc) + F["max_score"] * max(sc)
    if not (gts & set(tags)):
        adj *= 0.9
    if max(sc) < 0.2:
        adj *= 0.5
    n_u = len(unique)
    adj *= 0.85 if n_u < 1 else 0.9 if n_u < 2 else 0.95 if n_u < 3 else 1.0
    return float(adj)


def main(n, per):
    llml = get_llm_backend(); rng = random.Random(1210)
    rows = json.load(open("/opt/readyai_lab/convs.json")); rng.shuffle(rows)   # convs.parquet → json once (the miner venv has no pyarrow)
    res, used = {}, 0
    for row in rows:
        if used >= n:
            break
        lines = lines_of(row)[:150]
        if len(lines) < 30:
            continue
        enr = enrichment_lines(llml, lines, rng)
        gt, centre = ground_truth(llml, lines, enr)
        if not gt or centre is None:
            print("gt failed", flush=True); continue
        used += 1
        wins = [lines[i:i + 10] for i in range(0, len(lines) - 2, 8) if len(lines[i:i + 10]) >= 4]
        for w in rng.sample(wins, min(per, len(wins))):
            live = list(dict.fromkeys(miner_answer(llml, w, enr)))
            if len(live) < 3:
                continue
            safe = list(dict.fromkeys(t for t in (Utils.get_safe_tag(x) for x in live) if 3 <= len(t) <= 64))
            vec = vec_of(llml, list(set(live) | set(safe)))
            own_c = np.mean([vec[t] for t in safe if t in vec], axis=0)
            near = sorted(safe, key=lambda t: -float(own_c @ vec[t] / (np.linalg.norm(own_c) * np.linalg.norm(vec[t]))) if t in vec else 9)
            variants = {"live (combine, all tags)": live, "live, pre-cleaned": safe}
            for k in (4, 6, 8, 12):
                variants[f"pre-cleaned, trim to {k} nearest"] = near[:k]
            for name, tags in variants.items():
                scored = llml.validate_tag_set(tags) or []                    # what the validator actually scores (format_results)
                res.setdefault(name, []).append(score(gt, centre, scored, vec))
                res.setdefault("_kept " + name, []).append(len(scored) / max(len(tags), 1))
            res.setdefault("_n_live_tags", []).append(len(live)); res.setdefault("_n_both", []).append(len(set(gt) & set(live)))
        print(f"conversation {used}/{n}: gt {len(gt)} tags, enrichment {len(enr)} lines", flush=True)
    base = np.array(res["live (combine, all tags)"])
    print(f"live answers: {np.mean(res['_n_live_tags']):.1f} tags, {np.mean(res['_n_both']):.1f} exact matches with ground truth")
    for k in [k for k in res if not k.startswith("_")]:
        print(f"  (validator kept {np.mean(res['_kept ' + k]):.0%} of the tags sent)", end="  ")
        a = np.array(res[k]); d = a - base
        t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)) + 1e-12) if len(d) > 1 else 0
        print(f"{k:34} n={len(a):3} mean={a.mean():.4f} vs live {100 * (a.mean() / base.mean() - 1):+6.1f}%  cubed {100 * ((a.mean() / base.mean()) ** 3 - 1):+6.1f}%  paired t={t:.1f}")
    json.dump({k: list(map(float, v)) for k, v in res.items()}, open("/opt/readyai_lab/lab_final.json", "w"))


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]))
