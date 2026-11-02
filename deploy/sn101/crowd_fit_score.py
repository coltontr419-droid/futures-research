"""SN101 crowd-fit lab, step 2 (lab box; decisions.md §1211): which candidate crowd reproduces our observed live gaps?

For each hypothesis (one generator, or a mix "a+b" / "a:3+b:1"), per post: a crowd of 240 miners drawn from the generators' sampled answers (the
real field is ≈ 248, so the repeated-set penalty runs at its live c = 50), plus our five strategies as extra miners: m3 / m4 / m5's actual live
answers and fresh draws of m2's stock / entity prompts on gpt-4o-mini (never part of the crowd). The validator's TagScorer scores the post.
Gap = mean over posts of (ours − crowd mean): the crowd's members are i.i.d. per post, so the median miner's 24 h mean ≈ the crowd mean.

Observed live gaps (24 h on own answers, ln(usd / median) / 10 at 19:00 UTC 11-01 for m3-m5; §1190 for m2): m3 −0.340 (but m3 missed ≈ 11% of
rounds, which count 0: predicted live = 0.89·score − crowd), m4 −0.320, m5 −0.267, stock / entity on gpt-4o-mini ≈ −0.28.

    OMP_NUM_THREADS=2 nice -n 19 /opt/sn101lab/venv/bin/python crowd_fit_score.py crowd_fit.jsonl <hyp> [<hyp> ...]
"""
import json
import os
import random
import sys
import time

import numpy as np
import torch

torch.set_num_threads(2)
sys.path.insert(0, "/opt/sn101lab")
from tag101.tasks.sn101 import REFERENCE_MODEL_NAME, SN101_MAX_TAGS  # noqa: E402
from tag101.tasks.sn101_reference.core.scoring import TagScorer  # noqa: E402

CROWD = 240
OURS = ["m3", "m4", "m5", "ours_ref_4omini", "ours_ent_4omini"] + [x for x in os.getenv("EXTRA_OURS", "").split(",") if x]
OBS = {"m3": -0.340, "m4": -0.320, "m5": -0.267, "ours_ref_4omini": -0.28, "ours_ent_4omini": -0.28}
MISS = {"m3": 0.11}


def parse(h):
    parts = [x.split(":") for x in h.split("+")]
    return [(p[0], float(p[1]) if len(p) > 1 else 1.0) for p in parts]


def main(path, hyps):
    recs = [json.loads(l) for l in open(path)]
    if os.getenv("NO_REPEAT_PENALTY"):          # the candidates give only 3-6 distinct sets in 8 draws, so a 240-miner crowd holds 40-80 copies of
        import tag101.tasks.sn101_reference.core.scoring.tag_scorer as ts   # each and the clone penalty crushes it; a real field varies its
        ts.repeated_set_adjustment = lambda count, **kw: 1.0                 # answers to avoid that, so score the crowd without the penalty
    scorer = TagScorer(model_name=REFERENCE_MODEL_NAME, n_tags_per_miner=SN101_MAX_TAGS)
    out = {}
    for h in hyps:
        mix = parse(h); w = np.array([x[1] for x in mix]); w = w / w.sum()
        ours_s = {o: [] for o in OURS}; crowd_mean = []; crowd_sd = []; t0 = time.time()
        for i, r in enumerate(recs):
            pools = [r["gens"].get(g) for g, _ in mix]
            if not all(pools) or not all(k in r["ours"] for k in OURS[3:]):
                continue
            rng = random.Random(f"{h}|{i}")
            crowd = [list(rng.choice(pools[rng.choices(range(len(mix)), weights=w)[0]])) for _ in range(CROWD)]
            ours = [r["live"][o] if o in r["live"] else r["ours"][o] for o in OURS]
            s = scorer.score(r["post"], crowd + ours).get("miner_scores", [])
            if len(s) < CROWD + len(OURS):
                continue
            cm = float(np.mean(s[:CROWD])); crowd_mean.append(cm); crowd_sd.append(float(np.std(s[:CROWD])))
            for o, v in zip(OURS, s[CROWD:]):
                ours_s[o].append(float(v))
        cm = float(np.mean(crowd_mean))
        pred = {o: (1 - MISS.get(o, 0.0)) * float(np.mean(v)) - cm for o, v in ours_s.items()}
        se = {o: float(np.std(np.array(v) - np.array(crowd_mean), ddof=1) / np.sqrt(len(v))) for o, v in ours_s.items()}
        rmse = float(np.sqrt(np.mean([(pred[o] - OBS[o]) ** 2 for o in OURS if o in OBS])))
        diffs_obs = np.array([OBS["m5"] - OBS["m4"], OBS["m4"] - OBS["m3"]]); diffs = np.array([pred["m5"] - pred["m4"], pred["m4"] - pred["m3"]])
        out[h] = {"n": len(crowd_mean), "crowd_mean": cm, "crowd_sd_within_post": float(np.mean(crowd_sd)), "pred": pred, "se": se, "rmse": rmse,
                  "order_rmse": float(np.sqrt(np.mean((diffs - diffs_obs) ** 2)))}
        print(f"{h:34} n={len(crowd_mean):3} crowd {cm:.3f} | " + " ".join(f"{o.replace('ours_', '')} {pred[o]:+.3f}" for o in OURS) +
              f" | rmse {rmse:.3f} order {out[h]['order_rmse']:.3f} | {time.time() - t0:.0f}s", flush=True)
        with open(path.replace(".jsonl", "_scores_nopen.jsonl" if os.getenv("NO_REPEAT_PENALTY") else "_scores.jsonl"), "a") as f:
            f.write(json.dumps({"hyp": h, **out[h]}) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
