"""ReadyAI skill_coverage_evaluation lab (decisions.md §1199). For each logged task (TASK_LOG, run_miner.py), build answers with variants of the
miner pipeline and score every one through the validator's own path: SkillCoverageEvaluationTaskBundle.format_results (gpt-5.2 judge pass,
embeddings; validators are locked to the in-code defaults) then SkillCoverageScoringMechanism. Sections: ALL of the task's sections are scored
(validators score 3 random ones), the same for every variant.

Variants: A = the logged live answer (luna fast bundle, 2 tests/section); B = luna fast bundle asked for 4 tests/section; C = the fast bundle on
gpt-5.2 (2 tests); D = gpt-5.2, 4 tests.

    set -a; . /opt/tag101/openai.env; set +a; /opt/readyai/venv/bin/python skill_lab.py /opt/readyai/tasks_r1.jsonl,/opt/readyai/tasks_r2.jsonl
"""

import asyncio
import json
import re
import statistics as st
import sys

sys.path.insert(0, "/opt/readyai/repo")
from conversationgenome.ConfigLib import c  # noqa: E402

c.set("system", "llm_overrides_locked", True)          # backend = the validator's: LlmOpenAI(ignore_model_override=True), gpt-5.2

from conversationgenome.api.models.skill_coverage import SectionMapEntry, SkillCoverageMetadata  # noqa: E402
from conversationgenome.llm import prompt_manager as pm_mod  # noqa: E402
from conversationgenome.llm.llm_factory import get_llm_backend  # noqa: E402
from conversationgenome.llm.llm_openai import LlmOpenAI  # noqa: E402
from conversationgenome.scoring_mechanism.SkillCoverageScoringMechanism import SkillCoverageScoringMechanism  # noqa: E402
from conversationgenome.task.SkillCoverageEvaluationTask import SkillCoverageEvaluationTask  # noqa: E402
from conversationgenome.task_bundle.SkillCoverageEvaluationTaskBundle import (  # noqa: E402
    SkillCoverageEvaluationTaskBundle, SkillCoverageInput, SkillCoverageInputData)

FOUR = ("3.  **Section tests: write 4 tests per section** (core cases plus edge/failure cases), each verifying a distinct behavior with a "
        "distinct, concrete, verifiable assertion; never more than 5. Only tests the judge accepts as correct count, so every test must be "
        "checkable against the skill text you write.")
_pm = pm_mod.prompt_manager if hasattr(pm_mod, "prompt_manager") else pm_mod
_orig_prompt = type(_pm).skill_request_to_skill_bundle_prompt


def _four(self, *a, **k):
    return re.sub(r"3\.\s+\*\*Section tests:.*?(?=\n\s*4\.)", FOUR, _orig_prompt(self, *a, **k), flags=re.S)


def answer(task_input: dict, model: str, four: bool) -> dict:
    """The stock fast path (SkillCoverageEvaluationTask._mine_fast) with the model and the tests-per-section instruction varied."""
    llml = LlmOpenAI(ignore_model_override=True)
    if model != "luna":                                 # skip the @model_override('gpt-5.6-luna') wrapper: run on gpt-5.2
        llml.skill_request_to_skill_bundle = LlmOpenAI.skill_request_to_skill_bundle.__wrapped__.__get__(llml)
    type(_pm).skill_request_to_skill_bundle_prompt = _four if four else _orig_prompt
    try:
        task = SkillCoverageEvaluationTask(mode="lab", type="skill_coverage_evaluation", input=task_input)
        return task._mine_fast(llml, task.input.data.seed, task.input.data.section_map)
    finally:
        type(_pm).skill_request_to_skill_bundle_prompt = _orig_prompt


async def score(task_input: dict, answers: dict) -> dict:
    sections = [SectionMapEntry(**s) for s in task_input["data"]["section_map"]]
    llml = get_llm_backend()
    vectors = llml.get_vector_embeddings_batch([f"{s.title}: {s.description}" for s in sections])
    bundle = SkillCoverageEvaluationTaskBundle(
        mode="lab", type="skill_coverage_evaluation",
        input=SkillCoverageInput(guid=str(task_input["guid"]), data=SkillCoverageInputData(
            lines=[(0, json.dumps({"seed": task_input["data"]["seed"]}))], total=1, participants=[],
            seed=task_input["data"]["seed"], section_map=sections),
            metadata=SkillCoverageMetadata(sections=sections, section_vectors={s.section_id: (v or []) for s, v in zip(sections, vectors)})))
    names = list(answers)
    formatted = [[await bundle.format_results(json.loads(json.dumps(answers[n])))] for n in names]
    final, _ = await SkillCoverageScoringMechanism().evaluate(bundle, formatted)
    return {n: (f["final_miner_score"], sum(len(v) for v in (a.get("section_tests") or {}).values())) for n, f, a in zip(names, final, answers.values())}


def main(paths: str) -> None:
    rows = [json.loads(l) for p in paths.split(",") for l in open(p)]
    tasks = [r for r in rows if r["type"] == "skill_coverage_evaluation" and r.get("input")]
    res = {}
    for i, r in enumerate(tasks):
        ti = r["input"]
        answers = {"A live (luna, 2/section)": r["output"], "B luna, 4/section": answer(ti, "luna", True),
                   "C gpt-5.2, 2/section": answer(ti, "gpt-5.2", False), "D gpt-5.2, 4/section": answer(ti, "gpt-5.2", True)}
        s = asyncio.run(score(ti, answers))
        for n, (sc, nt) in s.items():
            res.setdefault(n, []).append(sc)
        print(f"task {i + 1}/{len(tasks)}: " + " | ".join(f"{n.split(' ')[0]} {sc:.3f} ({nt} tests)" for n, (sc, nt) in s.items()), flush=True)
    base = st.mean(res["A live (luna, 2/section)"])
    for n, v in res.items():
        m = st.mean(v)
        print(f"{n:26} mean {m:.3f}  vs live {100 * (m / base - 1):+.1f}%" if base else f"{n:26} mean {m:.3f}")


if __name__ == "__main__":
    main(sys.argv[1])
