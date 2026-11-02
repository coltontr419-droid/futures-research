"""ReadyAI tagging lab, round 5 (decisions.md §1211): steer the final answer toward the enrichment. The validator's search queries are written
from the FULL conversation, so the enrichment snippets the miner receives are its only view of the part of the ground truth it cannot see (the
10-line window covers a fraction of it). Same setup as lab_final.py (full-conversation ground truth built the validator's way, synthesized
enrichment, validate_tag_set then the scoring formula); variants of the post-combine selection, K = 12 tags each (live keeps 12):

  live          pre-clean, the 12 nearest the centroid of our own combined answer (scoring_fixes.trim_central, deployed)
  enr centre    the 12 of the combined answer nearest the centroid of the enrichment tags alone
  blend a       the 12 nearest a·enrichment centroid + (1 − a)·own centroid (a = 0.5, 0.75)
  enr + window  the 12 nearest the enrichment centroid from the pool of combined + raw window + raw enrichment tags (more candidates)

    cd /opt/readyai_lab && LLM_TYPE_OVERRIDE=openai OPENAI_MODEL=gpt-5.2 /opt/readyai/venv/bin/python lab_enr.py <n conversations> <windows each>
"""
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import lab_final as LF
import central15  # noqa: F401
from conversationgenome.api.models.conversation import Conversation
from conversationgenome.llm.llm_factory import get_llm_backend
from conversationgenome.utils.Utils import Utils

K = 12
safe = lambda tags: list(dict.fromkeys(t for t in (Utils.get_safe_tag(str(x)) for x in tags or []) if 3 <= len(t) <= 64))
unit = lambda v: v / (np.linalg.norm(v) + 1e-12)


def miner_parts(llml, window, enr):
    """The live pipeline (lab_final.miner_answer), keeping the window tags and the enrichment tags apart."""
    result = llml.conversation_to_metadata(conversation=Conversation(guid="lab", lines=window), generateEmbeddings=False)
    win = result.tags if result else []
    prev = central15._fast(llml)
    try:
        with ThreadPoolExecutor(min(8, max(len(enr), 1))) as ex:
            outs = list(ex.map(lambda c: llml.enrichment_to_metadata(c, generateEmbeddings=False), [c for _, c in enr]))
        etags = [t for o in outs if o and o.tags for t in o.tags]
        combined = llml.combine_metadata_tags(([win] if win else []) + [o.tags for o in outs if o and o.tags], generateEmbeddings=False)
    finally:
        for k, v in prev.items():
            setattr(llml, k, v)
    return safe(combined.tags if combined else win), safe(win), safe(etags)


def main(n, per):
    llml = get_llm_backend(); rng = random.Random(int(os.getenv("SEED", "1211")))
    import json
    rows = json.load(open("/opt/readyai_lab/convs.json")); rng.shuffle(rows)
    res, used = {}, 0
    for row in rows:
        if used >= n:
            break
        lines = LF.lines_of(row)[:150]
        if len(lines) < 30:
            continue
        enr = LF.enrichment_lines(llml, lines, rng)
        if not enr:
            continue
        gt, centre = LF.ground_truth(llml, lines, enr)
        if not gt or centre is None:
            continue
        used += 1
        wins = [lines[i:i + 10] for i in range(0, len(lines) - 2, 8) if len(lines[i:i + 10]) >= 4]
        for w in rng.sample(wins, min(per, len(wins))):
            comb, win, etags = miner_parts(llml, w, enr)
            if len(comb) < 5 or not etags:
                continue
            vec = LF.vec_of(llml, list(set(comb) | set(win) | set(etags)))
            have = lambda ts: [t for t in ts if t in vec]
            own_c = unit(np.mean([vec[t] for t in have(comb)], axis=0)); enr_c = unit(np.mean([vec[t] for t in have(etags)], axis=0))
            near = lambda pool, c: sorted(have(pool), key=lambda t: -float(unit(vec[t]) @ c))[:K]
            variants = {"live (own centre)": near(comb, own_c), "enr centre": near(comb, enr_c)}
            for a in (0.5, 0.75):
                variants[f"blend {a}"] = near(comb, unit(a * enr_c + (1 - a) * own_c))
            wide = list(dict.fromkeys(comb + win + etags))
            variants["enr centre, wider pool"] = near(wide, enr_c)
            variants["wider pool, K 15"] = sorted(have(wide), key=lambda t: -float(unit(vec[t]) @ enr_c))[:15]
            variants["enrichment tags only"] = near(etags, enr_c)
            variants["no combine (window + enrichment)"] = near(list(dict.fromkeys(win + etags)), enr_c)
            for name, tags in variants.items():
                scored = llml.validate_tag_set(tags) or []
                res.setdefault(name, []).append(LF.score(gt, centre, scored, vec))
        print(f"conversation {used}/{n}: " + " | ".join(f"{k} {v[-1]:.3f}" for k, v in res.items()), flush=True)
    base = np.array(res["live (own centre)"])
    for name, v in res.items():
        a = np.array(v); d = a - base
        t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)) + 1e-12) if len(d) > 1 else 0
        print(f"{name:24} n={len(a)} mean {a.mean():.4f} ({100 * (a.mean() / base.mean() - 1):+.1f}% vs live, cubed {100 * ((a.mean() / base.mean()) ** 3 - 1):+.1f}%, paired t {t:.1f})")
    json.dump(res, open(f"/opt/readyai_lab/lab_enr_{os.getenv('SEED', '1211')}.json", "w"))


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]))
