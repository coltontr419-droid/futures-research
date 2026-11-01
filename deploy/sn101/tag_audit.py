"""Tag101 crowd-independent audit (futures-research decisions.md §1208): for every tag each live strategy actually sent (m3 modal / m4 stock on
gpt-5-mini / m5 extract, same posts), the validator's own validity tier (closeness to the post x format) and label fitness (the 30% of
utility that ignores the crowd), plus how the three strategies' tags cluster when pooled per post (indicative only: 3 miners is not the crowd).

    ~/sn101lab/venv/bin/python tag_audit.py data/posts_m3.jsonl data/posts_m4.jsonl data/posts_m5.jsonl
"""
import json
import sys
from collections import defaultdict

import numpy as np

from tag101.tasks.sn101_reference.core.scoring.preprocessing import build_scoring_context
from tag101.tasks.sn101_reference.core.scoring.utility import label_fitness
from tag101.tasks.sn101_reference.core.scoring.validity import ValidityScorer

names = [p.split("posts_")[-1].split(".")[0] for p in sys.argv[1:]]
by_post = defaultdict(dict)
for name, p in zip(names, sys.argv[1:]):
    for line in open(p):
        r = json.loads(line)
        by_post[r["post"]][name] = r["tags"]
posts = [p for p, d in by_post.items() if len(d) == len(names)]
print(f"posts answered by all of {names}: {len(posts)}")
vs = ValidityScorer()
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except Exception:
    nlp = None
print("spaCy for label fitness:", "yes" if nlp else "no (lexical fallback)")
stats = {n: defaultdict(list) for n in names}
for post in posts:
    responses = [by_post[post][n] for n in names]
    ctx = build_scoring_context(post=post, responses=responses, n_tags_per_miner=3)
    res = vs.score_from_context(ctx)
    for n, tags, vals, det in zip(names, ctx.normalized_responses, res["validity_scores"], res["validity_details"]):
        s = stats[n]
        s["n_tags"].append(len(tags))
        for t, v, d in zip(tags, vals, det):
            s["validity"].append(v); s["format"].append(d["format_score"]); s["lexical"].append(d["lexical_overlap"])
            s["sim_post"].append(d["sim_post"]); s["fitness"].append(label_fitness(t, nlp))
            s["glued"].append(" " not in t and "-" not in t and len(t) > 12)
        if len(tags) >= 2:                                 # redundancy: only a miner's best tag per cluster counts (≤ 8 clusters per post)
            E = vs._embed_texts(list(tags)); S = E @ E.T; iu = np.triu_indices(len(tags), 1)
            s["max_pair_sim"].append(float(S[iu].max())); s["same_cluster_pair"].append(bool((S[iu] >= 0.70).any()))
            s["mean_pair_sim"].append(float(S[iu].mean()))
for n in names:
    s = stats[n]; v = np.array(s["validity"])
    print(f"== {n}: tags kept after preprocessing per answer {np.mean(s['n_tags']):.2f} | validity mean {v.mean():.3f} "
          f"(tier 1.0 {np.mean(v == 1.0):.0%}, 0.6 {np.mean(v == 0.6):.0%}, 0.3 {np.mean(v == 0.3):.0%}, 0 {np.mean(v == 0):.0%}) | "
          f"format pass {np.mean(s['format']):.0%} | lexical overlap {np.mean(s['lexical']):.2f} | label fitness {np.mean(s['fitness']):.3f} | "
          f"glued {np.mean(s['glued']):.0%}")
    print(f"   own-tag redundancy: mean pairwise cosine {np.mean(s['mean_pair_sim']):.2f}, max pair {np.mean(s['max_pair_sim']):.2f}; "
          f"answers with a pair ≥ 0.70 (same cluster at the 0.30 distance threshold) {np.mean(s['same_cluster_pair']):.0%}")
