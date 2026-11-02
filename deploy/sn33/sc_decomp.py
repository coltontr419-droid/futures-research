"""ReadyAI skill coverage: where does the deployed answer lose? (§1211 addendum). Logged r3 tasks → sc_lab2.self_judged (the deployed
anchor + own-judge logic) → the validator's pipeline, reporting section coverage, skill coverage, penalties and judged accuracy separately.

    LLM_TYPE_OVERRIDE=openai OPENAI_MODEL=gpt-5.2 python sc_decomp.py /opt/readyai/tasks_r3.jsonl <n>
"""
import json
import os
import random
import sys

import numpy as np

import sc_lab2 as L
from conversationgenome.api.models.skill_coverage import SectionMapEntry
from conversationgenome.task_bundle.SkillCoverageEvaluationTaskBundle import MAX_SKILL_CHARS, PER_SECTION_TEST_CAP, SkillCoverageEvaluationTaskBundle


def parts(task_input, answer, evaluated):
    sm = [SectionMapEntry(**s) for s in task_input["section_map"]]; ev = [s for s in sm if s.section_id in evaluated]
    sv = dict(zip([s.section_id for s in ev], L.llml.get_vector_embeddings_batch([f"{s.title}: {s.description}" for s in ev])))
    skill = (answer.get("skill") or "")[:MAX_SKILL_CHARS]
    tests = {sid: [x for x in (SkillCoverageEvaluationTaskBundle._sanitize_test(t) for t in ts) if x]
             for sid, ts in (answer.get("section_tests") or {}).items() if sid in evaluated and isinstance(ts, list)}
    elig = {sid: ts[:PER_SECTION_TEST_CAP] for sid, ts in tests.items()}
    j = L.llml.judge_section_tests(skill, ev, elig) if elig and skill.strip() else None
    verdict = {(sid, v.name): v.correct for sid, vs in (j.verdicts.items() if j else []) for v in vs}
    slots = [(sid, i) for sid, ts in elig.items() for i, _ in enumerate(ts)]
    V = L.llml.get_vector_embeddings_batch([skill] + [L.etext(elig[s][i]) for s, i in slots])
    tv = {sid: [] for sid in tests}
    for (sid, i), v in zip(slots, V[1:]):
        t = elig[sid][i]; tv[sid].append({"name": t["name"], "vector": v, "judged_correct": verdict.get((sid, t["name"]), False)})
    total = sum(len(x) for x in tv.values())
    secs = L.M._score_sections(sv, tv); cov = float(np.mean(list(secs.values()))) if secs else 0.0
    sk = L.M._score_skill_coverage(V[0], tv); adj = L.M._calculate_adjusted_score(cov, sk)
    final = L.M._calculate_penalty(adj, total_tests=total, sections_addressed=sum(1 for s in secs.values() if s > 0), test_vectors=tv) if total >= L.M.min_tests else 0.0
    acc = sum(t["judged_correct"] for x in tv.values() for t in x) / max(total, 1)
    best1 = [max([L.cos(sv[sid], t["vector"]) for t in tv.get(sid, [])] or [0]) for sid in sv]
    return dict(final=final, section=cov, skill=sk, adjusted=adj, penalty=final / adj if adj else 0, acc=acc, tests=total,
                zero_sections=sum(1 for s in secs.values() if s == 0), best_test_cos=float(np.mean(best1)))


def with_contract(answer):
    """Append each kept test's claim to the skill document as an explicit behaviour contract (no model call; stays under MAX_SKILL_CHARS)."""
    lines = [f"- {t.get('description', '').strip()}: {t.get('assertion', '').strip()}" for ts in (answer.get("section_tests") or {}).values()
             for t in ts if (t.get("assertion") or "").strip()]
    skill = (answer.get("skill") or "").rstrip()
    block = "\n\n## Behavior contract\n" + "\n".join(lines)
    return {**answer, "skill": (skill + block)[:MAX_SKILL_CHARS] if skill else skill}


def main(path, n):
    rows = [json.loads(l) for l in open(path) if "\"skill_coverage_evaluation\"" in l][int(os.getenv("START", "0")):][:n]
    rng = random.Random(1211); out = []
    for k, r in enumerate(rows):
        inp, o = r["input"]["data"], r["output"] or {}
        if not o.get("section_tests"):
            continue
        ev = set(s["section_id"] for s in rng.sample(inp["section_map"], min(3, len(inp["section_map"]))))
        ans = {**o, "section_tests": L.self_judged(o.get("skill") or "", inp["section_map"], o["section_tests"])}
        p = parts(inp, ans, ev); q = parts(inp, with_contract(ans), ev); out.append((p, q))
        print(f"task {k + 1}: deployed final {p['final']:.3f} acc {p['acc']:.2f} skill {p['skill']:.3f} | contract final {q['final']:.3f} "
              f"acc {q['acc']:.2f} skill {q['skill']:.3f}", flush=True)
    for i, name in enumerate(("deployed", "contract")):
        print(f"MEAN {name}: " + " ".join(f"{a} {np.mean([o[i][a] for o in out]):.3f}" for a in out[0][0]))
    d = np.array([o[1]["final"] - o[0]["final"] for o in out])
    print(f"contract − deployed: {d.mean():+.4f} ({100 * d.mean() / np.mean([o[0]['final'] for o in out]):+.1f}%), paired t {d.mean() / (d.std(ddof=1) / np.sqrt(len(d))):.1f}, n {len(d)}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
