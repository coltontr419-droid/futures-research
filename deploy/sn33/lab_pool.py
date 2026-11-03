"""ReadyAI tagging lab (§1211 add. 12): what seeing MORE windows of the same conversation is worth. The validator sends ≈ 5 windows of one
conversation (one bundle, same enrichment) to 6 random miners each, all scored against the same full-conversation ground truth; an operator
holding many UIDs receives most of them. Per conversation: answers built (live pipeline + near_enrichment pick, K 12) from 1, 2 and 5
windows' lines, scored against the validator-style ground truth.
    cd /opt/readyai_lab && LLM_TYPE_OVERRIDE=openai OPENAI_MODEL=gpt-5.2 /opt/readyai/venv/bin/python lab_pool.py <n conversations>
"""
import json, os, random, sys
import numpy as np
import lab_final as LF
import lab_enr as LE
from conversationgenome.llm.llm_factory import get_llm_backend
sys.path.insert(0, "/opt/readyai")
from scoring_fixes import near_enrichment, trim_central

def main(n):
    llml = get_llm_backend(); rng = random.Random(int(os.getenv("SEED", "1212")))
    rows = json.load(open("/opt/readyai_lab/convs.json")); rng.shuffle(rows)
    res, used = {}, 0
    for row in rows:
        if used >= n: break
        lines = LF.lines_of(row)[:150]
        if len(lines) < 60: continue
        enr = LF.enrichment_lines(llml, lines, rng)
        if not enr: continue
        gt, centre = LF.ground_truth(llml, lines, enr)
        if not gt or centre is None: continue
        wins = [lines[i:i + 10] for i in range(0, len(lines) - 2, 8) if len(lines[i:i + 10]) >= 4]
        pick = rng.sample(wins, 5); used += 1
        for name, w in (("1 window", pick[0]), ("2 windows", pick[0] + pick[1]), ("5 windows", [l for p in pick for l in p])):
            comb, win, etags = LE.miner_parts(llml, w, enr)
            tags = near_enrichment(llml, comb, win, etags) or trim_central(llml, comb)
            vec = LF.vec_of(llml, list(set(tags)))
            res.setdefault(name, []).append(LF.score(gt, centre, llml.validate_tag_set(tags) or [], vec))
        print(f"conversation {used}/{n}: " + " | ".join(f"{k} {v[-1]:.3f}" for k, v in res.items()), flush=True)
    base = np.array(res["1 window"])
    for k, v in res.items():
        a = np.array(v); d = a - base; t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)) + 1e-12) if len(d) > 1 else 0
        print(f"{k:10} n={len(a)} mean {a.mean():.4f} ({100 * (a.mean() / base.mean() - 1):+.1f}% vs 1 window, paired t {t:.1f})")
    json.dump(res, open("/opt/readyai_lab/lab_pool.json", "w"))

if __name__ == "__main__":
    main(int(sys.argv[1]))
