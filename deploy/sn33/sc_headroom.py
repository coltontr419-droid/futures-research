"""Skill coverage headroom (decisions.md §1210): on logged r3 answers, the validator's section score (mean of the top-2 tests' cosine to
"{title}: {description}", embedded as the validator does) for our live tests vs tests whose description IS the section text (same assertion),
and skill coverage (cosine of the mean test vector to our skill text). Judge not applied (all tests assumed correct); the max pairwise test
cosine is printed against the 0.95 near-duplicate threshold.

    LLM_TYPE_OVERRIDE=openai OPENAI_MODEL=gpt-5.2 python sc_headroom.py /opt/readyai/tasks_r3.jsonl
"""
import json
import sys

import numpy as np

sys.path.insert(0, "/opt/readyai/repo")
from conversationgenome.llm.llm_factory import get_llm_backend  # noqa: E402

llml = get_llm_backend()
cos = lambda a, b: float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
text = lambda d, a: f"{d}\nAssertion: {a}".strip() if (a or "").strip() else d
rows = [json.loads(l) for l in open(sys.argv[1]) if '"skill_coverage_evaluation"' in l]
out = {"live": [], "section text as description": []}; skill = []; dup_live = []; dup_alt = []
for r in rows:
    secs = {s["section_id"]: f"{s['title']}: {s['description']}" for s in r["input"]["data"]["section_map"]}
    tests = (r["output"] or {}).get("section_tests") or {}
    sk = (r["output"] or {}).get("skill") or ""
    items = [(sid, text(t.get("description", ""), t.get("assertion", "")), text(secs[sid], t.get("assertion", ""))) for sid, ts in tests.items() if sid in secs for t in ts[:6]]
    if not items:
        continue
    texts = list(secs.values()) + [x[1] for x in items] + [x[2] for x in items] + [sk]
    V = [np.asarray(v) for v in llml.get_vector_embeddings_batch(texts)]
    sv = dict(zip(secs, V[:len(secs)])); lv = V[len(secs):len(secs) + len(items)]; av = V[len(secs) + len(items):-1]; skv = V[-1]
    for name, vecs in (("live", lv), ("section text as description", av)):
        per = []
        for sid in secs:
            s = sorted((cos(sv[sid], v) for (i, v) in zip(items, vecs) if i[0] == sid), reverse=True)[:2]
            per.append(np.mean(s) if s else 0.0)
        out[name].append(np.mean(per))
    skill.append(cos(np.mean(lv, axis=0), skv))
    dup_live.append(max((cos(a, b) for i, a in enumerate(lv) for b in lv[i + 1:]), default=0))
    dup_alt.append(max((cos(a, b) for i, a in enumerate(av) for b in av[i + 1:]), default=0))
for k, v in out.items():
    print(f"{k:30} section coverage mean {np.mean(v):.3f} (n {len(v)})")
print(f"live skill coverage mean {np.mean(skill):.3f}")
print(f"max pairwise test cosine: live median {np.median(dup_live):.3f} (≥ 0.95 in {np.mean(np.array(dup_live) >= .95):.0%}); section-text tests median {np.median(dup_alt):.3f} (≥ 0.95 in {np.mean(np.array(dup_alt) >= .95):.0%})")
