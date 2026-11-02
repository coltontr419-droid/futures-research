"""SN101 crowd-fit lab, step 4b (lab box; §1211 addendum): selection rules from the stored verbatim draws, embedded with the scorer's own
MiniLM. Writes the picks into "ours" → crowd_fit_cands3.jsonl for crowd_fit_score.py (EXTRA_OURS).

  ours_vmodal      5 draws, the 3 phrases given most often (ties: nearest the pool centroid)
  ours_vcentral    5 draws pooled, the 3 phrases nearest the pool centroid
  ours_v6central   one 6-phrase answer, the 3 nearest its centroid
  ours_vfirst      the first draw alone (= the live m3 recipe; a fresh check of the −0.03..−0.05 read)
"""
import json
import sys
from collections import Counter

import numpy as np
from sentence_transformers import SentenceTransformer

m = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
norm = lambda t: " ".join(str(t).lower().split())


def central(tags, k=3):
    tags = list(dict.fromkeys(norm(t) for t in tags if norm(t)))
    if len(tags) <= k:
        return tags
    v = m.encode(tags, normalize_embeddings=True); c = v.mean(axis=0)
    return [tags[i] for i in np.argsort(-(v @ c))[:k]]


with open(sys.argv[2], "w") as f:
    for line in open(sys.argv[1]):
        r = json.loads(line); d = r.get("draws_verb5") or []
        if len(d) < 3 or not r.get("verb6"):
            continue
        pool = [norm(t) for x in d for t in x]
        cnt = Counter(pool); cen = central(pool, k=len(set(pool)))
        rank = {t: i for i, t in enumerate(cen)}
        r["ours"]["ours_vmodal"] = sorted(cnt, key=lambda t: (-cnt[t], rank.get(t, 99)))[:3]
        r["ours"]["ours_vcentral"] = cen[:3]
        r["ours"]["ours_v6central"] = central(r["verb6"])
        r["ours"]["ours_vfirst"] = [norm(t) for t in d[0]][:3]
        f.write(json.dumps(r) + "\n")
