"""SN101 crowd-fit lab, step 3 (droplet; decisions.md §1211): candidate answers for a new slot, drawn separately from the crowd (never part of
it), added to crowd_fit.jsonl as extra "ours_*" strategies → crowd_fit_cands.jsonl, then scored inside the best-fitting crowd.

    /opt/tag101/venv/bin/python crowd_fit_add.py
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/opt/tag101")
from crowd_fit_gen import VERBATIM, chat  # noqa: E402

CANDS = {"ours_verb_4omini": (VERBATIM, "gpt-4o-mini"), "ours_verb_4omini_b": (VERBATIM, "gpt-4o-mini"), "ours_verb_41mini": (VERBATIM, "gpt-4.1-mini"),
         "ours_verb_4o": (VERBATIM, "gpt-4o")}


def main():
    recs = [json.loads(l) for l in open("/opt/tag101/crowd_fit.jsonl")]
    with open("/opt/tag101/crowd_fit_cands.jsonl", "w") as f, ThreadPoolExecutor(16) as ex:
        for i, r in enumerate(recs):
            res = list(ex.map(lambda c: chat(c[0], r["post"], c[1]), CANDS.values()))
            r["ours"].update({k: v for k, v in zip(CANDS, res) if v})
            f.write(json.dumps(r) + "\n")
            print(f"{i + 1}/{len(recs)}", flush=True)


if __name__ == "__main__":
    main()
