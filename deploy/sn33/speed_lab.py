"""ReadyAI conversation_tagging speed lab (decisions.md §1201): validators wait task.timeout = 12 s; live, 28% of our conversation answers took
longer and scored zero. Replays logged conversation tasks (TASK_LOG) through ConversationTaggingTask.mine()'s logic with the miner backend
(gpt-5.2) and times each variant end to end. Variants: stock tagging; central15 as live; central15 at low reasoning + priority tier;
the same with the enrichment calls run in parallel.

    set -a; . /opt/tag101/openai.env; set +a; OPENAI_MODEL=gpt-5.2 LLM_TYPE_OVERRIDE=openai /opt/readyai/venv/bin/python speed_lab.py <tasks.jsonl,...> [n]
"""

import json
import statistics as st
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/opt/readyai"); sys.path.insert(0, "/opt/readyai/repo")
from conversationgenome.api.models.conversation import Conversation  # noqa: E402
from conversationgenome.llm.LlmLib import LlmLib  # noqa: E402
from conversationgenome.llm.llm_factory import get_llm_backend  # noqa: E402

STOCK = LlmLib.conversation_to_metadata
import central15  # noqa: E402  (patches LlmLib.conversation_to_metadata)

CENTRAL = LlmLib.conversation_to_metadata


def run(data: dict, cats, central: bool, fast: bool, parallel: bool) -> tuple[float, list]:
    LlmLib.conversation_to_metadata = CENTRAL if central else STOCK
    llml = get_llm_backend()
    if fast:
        llml.reasoning_effort, llml.service_tier = "low", "priority"
    t0 = time.monotonic()
    conv = Conversation(guid="lab", lines=data["window"], miner_task_prompt="", input_categories=cats)
    result = llml.conversation_to_metadata(conversation=conv, generateEmbeddings=False)
    enr = data.get("enrichment_lines") or []
    tags = result.tags if result else []
    if enr:
        call = lambda content: llml.enrichment_to_metadata(content, generateEmbeddings=False, input_categories=cats)
        if parallel:
            with ThreadPoolExecutor(len(enr)) as ex:
                outs = list(ex.map(call, [c for _, c in enr]))
        else:
            outs = [call(c) for _, c in enr]
        sets = ([tags] if tags else []) + [o.tags for o in outs if o and o.tags]
        comb = llml.combine_metadata_tags(sets, generateEmbeddings=False) if sets else None
        tags = comb.tags if comb else tags
    return time.monotonic() - t0, tags


def main() -> None:
    rows = [json.loads(l) for p in sys.argv[1].split(",") for l in open(p)]
    tasks = [r["input"] for r in rows if r["type"] == "conversation_tagging"][: int(sys.argv[2]) if len(sys.argv) > 2 else 12]
    variants = {"stock": (False, False, False), "central15 live": (True, False, False), "central15 low+priority": (True, True, False),
                "central15 low+priority+parallel": (True, True, True)}
    res = {k: [] for k in variants}
    for i, ti in enumerate(tasks):
        for name, (c, f, p) in variants.items():
            secs, tags = run(ti["data"], ti.get("input_categories"), c, f, p)
            res[name].append(secs)
        print(f"task {i + 1}/{len(tasks)} enrichment {len(ti['data'].get('enrichment_lines') or [])}: "
              + " | ".join(f"{k} {v[-1]:.1f}s" for k, v in res.items()), flush=True)
    for k, v in res.items():
        v2 = sorted(v)
        print(f"{k:32} median {st.median(v):5.1f}s  p90 {v2[int(0.9 * (len(v2) - 1))]:5.1f}s  max {v2[-1]:5.1f}s  over 10 s: {sum(x > 10 for x in v)}/{len(v)}")


if __name__ == "__main__":
    main()
