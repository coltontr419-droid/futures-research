"""Skill coverage lab 2 (decisions.md §1210): replay logged r3 skill_coverage answers through the validator's exact pipeline
(SkillCoverageEvaluationTaskBundle.format_results: 3 random evaluated sections, sanitize, cap 6 per section, gpt-5.2 judge on the
evaluated sections, embed "{description}\\nAssertion: {assertion}", then SkillCoverageScoringMechanism's section / skill / penalty code)
for the live answer and for rewritten descriptions — same skill text and assertions, so the judge sees the same claims. The same random
sections per task for every variant (paired).

  live          as answered
  anchored      per section: test 1 description := "{title}: {description}" (the text the validator embeds as the section);
                test 2 := the candidate nearest the section whose cosine to test 1 stays < 0.94 (section text + live description, live
                + section text, live); further tests keep their live description; near-duplicate check on all pairs before answering

    LLM_TYPE_OVERRIDE=openai OPENAI_MODEL=gpt-5.2 python sc_lab2.py /opt/readyai/tasks_r3.jsonl [n tasks]
"""
import json
import random
import sys

import numpy as np

sys.path.insert(0, "/opt/readyai/repo")
from conversationgenome.api.models.skill_coverage import SectionMapEntry  # noqa: E402
from conversationgenome.llm.llm_factory import get_llm_backend  # noqa: E402
from conversationgenome.scoring_mechanism.SkillCoverageScoringMechanism import SkillCoverageScoringMechanism  # noqa: E402
from conversationgenome.task_bundle.SkillCoverageEvaluationTaskBundle import (  # noqa: E402
    MAX_SKILL_CHARS, PER_SECTION_TEST_CAP, SkillCoverageEvaluationTaskBundle)

llml = get_llm_backend(); M = SkillCoverageScoringMechanism()
cos = lambda a, b: float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
etext = lambda t: f"{t['description']}\nAssertion: {t['assertion']}".strip() if (t.get("assertion") or "").strip() else t["description"]


def anchored(section_map, section_tests):
    """The miner-side rewrite (deploy/sn33/central15.py anchor_tests mirrors this)."""
    secs = {s["section_id"]: f"{s['title']}: {s['description']}"[:1000] for s in section_map}
    out = {}
    for sid, tests in section_tests.items():
        tests = [dict(t) for t in tests[:PER_SECTION_TEST_CAP]]
        if sid not in secs or not tests:
            out[sid] = tests; continue
        st = secs[sid]; tests[0]["description"] = st
        if len(tests) > 1:
            live = tests[1]["description"]
            cands = [f"{st} {live}"[:1000], f"{live} {st}"[:1000], live]
            V = llml.get_vector_embeddings_batch([st] + [etext(tests[0])] + [etext({**tests[1], "description": c}) for c in cands])
            sv, t0 = np.asarray(V[0]), np.asarray(V[1])
            ok = [(cos(sv, v), c) for c, v in zip(cands, map(np.asarray, V[2:])) if cos(t0, v) < 0.94]
            tests[1]["description"] = max(ok)[1] if ok else live
        out[sid] = tests
    return out


def self_judged(skill, section_map, section_tests):
    """Anchor, then run the validator's judge prompt on our own tests (all sections; the miner cannot know which 3 are scored): the anchor
    description goes to a test the judge accepts, failing tests are dropped while a section keeps >= 2."""
    tests = anchored(section_map, section_tests)
    sm = [SectionMapEntry(**x) for x in section_map]
    j = llml.judge_section_tests(skill[:MAX_SKILL_CHARS], sm, {k: v[:PER_SECTION_TEST_CAP] for k, v in tests.items()})
    if not j:
        return tests
    ok = {(sid, v.name): v.correct for sid, vs in j.verdicts.items() for v in vs}
    secs = {x["section_id"]: f"{x['title']}: {x['description']}"[:1000] for x in section_map}
    out = {}
    for sid, ts in tests.items():
        good = [t for t in ts if ok.get((sid, t["name"]))]; bad = [t for t in ts if not ok.get((sid, t["name"]))]
        if good and sid in secs and good[0]["description"] != secs[sid]:
            orig = section_tests[sid]
            anchor = next((t for t in ts if t["description"] == secs[sid]), None)
            if anchor is not None and anchor in bad:                     # anchor text sits on a failed test: move it to a passing one
                anchor["description"] = next((o["description"] for o in orig if o["name"] == anchor["name"]), anchor["description"])
                good[0]["description"] = secs[sid]
        keep = good + bad[:max(0, 2 - len(good))]
        out[sid] = keep
    return out


def score(task_input, answer, evaluated):
    """format_results + evaluate for one answer, on the given evaluated sections."""
    section_map = [SectionMapEntry(**s) for s in task_input["section_map"]]
    ev_map = [s for s in section_map if s.section_id in evaluated]
    sv = dict(zip([s.section_id for s in ev_map], llml.get_vector_embeddings_batch([f"{s.title}: {s.description}" for s in ev_map])))
    skill = (answer.get("skill") or "")[:MAX_SKILL_CHARS]
    tests = {sid: [x for x in (SkillCoverageEvaluationTaskBundle._sanitize_test(t) for t in ts) if x]
             for sid, ts in (answer.get("section_tests") or {}).items() if sid in evaluated and isinstance(ts, list)}
    eligible = {sid: ts[:PER_SECTION_TEST_CAP] for sid, ts in tests.items()}
    j = llml.judge_section_tests(skill, ev_map, eligible) if eligible and skill.strip() else None
    verdict = {(sid, v.name): v.correct for sid, vs in (j.verdicts.items() if j else []) for v in vs}
    slots = [(sid, i) for sid, ts in eligible.items() for i, _ in enumerate(ts)]
    V = llml.get_vector_embeddings_batch([skill] + [etext(eligible[s][i]) for s, i in slots])
    tv = {sid: [] for sid in tests}
    for (sid, i), v in zip(slots, V[1:]):
        t = eligible[sid][i]; tv[sid].append({"name": t["name"], "vector": v, "judged_correct": verdict.get((sid, t["name"]), False)})
    total = sum(len(x) for x in tv.values())
    if total < M.min_tests:
        return 0.0, 0.0
    secs = M._score_sections(sv, tv); cov = float(np.mean(list(secs.values()))) if secs else 0.0
    sk = M._score_skill_coverage(V[0], tv)
    final = M._calculate_penalty(M._calculate_adjusted_score(cov, sk), total_tests=total, sections_addressed=sum(1 for s in secs.values() if s > 0),
                                 test_vectors=tv)
    acc = sum(t["judged_correct"] for x in tv.values() for t in x) / total
    return final, acc


def main(path, n):
    rows = [json.loads(l) for l in open(path) if '"skill_coverage_evaluation"' in l][:n]
    rng = random.Random(1210); res = {"live": [], "anchored": [], "anchored+self-judge": []}; acc = {k: [] for k in res}
    for k, r in enumerate(rows):
        inp, out = r["input"]["data"], r["output"] or {}
        if not out.get("section_tests"):
            continue
        ev = set(s["section_id"] for s in rng.sample(inp["section_map"], min(3, len(inp["section_map"]))))
        for name, ans in (("live", out), ("anchored", {**out, "section_tests": anchored(inp["section_map"], out["section_tests"])}),
                          ("anchored+self-judge", {**out, "section_tests": self_judged(out.get("skill") or "", inp["section_map"], out["section_tests"])})):
            s, a = score(inp, ans, ev); res[name].append(s); acc[name].append(a)
        print(f"task {k + 1}/{len(rows)}: " + " ".join(f"{n} {v[-1]:.3f}" for n, v in res.items()), flush=True)
    b = np.array(res["live"])
    for name in res:
        a = np.array(res[name]); d = a - b; t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)) + 1e-12) if len(d) > 1 else 0
        print(f"{name:9} n={len(a)} mean {a.mean():.4f} ({100 * (a.mean() / b.mean() - 1):+.1f}% vs live, paired t {t:.1f}) | judged correct {np.mean(acc[name]):.0%} | zeros {np.mean(a == 0):.0%}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 999)
