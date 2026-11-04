"""SN50 competition-level score (decisions.md §1217): the validator ranks a competition on the asset-WEIGHTED average of each miner's per-prompt
transformed scores (cap at the 90th percentile, minus the prompt's best), then softmax(beta). Rebuilds that from the cached field scores
(scores_<asset>_<days>.json) and our per-prompt CRPS (rows_<asset>_<days>.json, written by s50_backtest) for one model, and reports our
share vs the median UID.
    python -m futuresres.synth.s50_combined <days> <model> <beta> ASSET[:weight] ..."""
import json, sys
from collections import defaultdict
import numpy as np
from futuresres.synth.s50_backtest import CACHE
days, model, beta = int(sys.argv[1]), sys.argv[2], float(sys.argv[3])
W = {"SP500": 3.437935601155441, "AAPLX": 2.0916380815843123, "XAU": 1.7370922597118699, "GOOGLX": 1.6827392777257926, "TSLAX": 1.6068755936957768,
     "NVDAX": 1.6028217601617174, "WTIOIL": 0.8475062847978935, "SPCX": 0.4329342627683478, "BTC": 1.0, "ETH": 0.7064366394033871,
     "SOL": 0.6310037175639559, "XRP": 0.5658394110809131, "HYPE": 0.4784547133706857}
num, den, ours_num, ours_den, n = defaultdict(float), defaultdict(float), 0.0, 0.0, 0
for arg in sys.argv[4:]:
    asset = arg.split(":")[0]; w = float(arg.split(":")[1]) if ":" in arg else W[asset]
    pre = __import__("os").environ.get("S50_PREFIX", "")            # "1h" → the Crypto-1h files (scores1h_ / rows1h_) (§1222)
    field = json.loads((CACHE / f"scores{pre}_{asset}_{days}.json").read_text())
    rows = {r["start"]: r for r in json.loads((CACHE / f"rows{pre}_{asset}_{days}.json").read_text())}
    for st, r in rows.items():
        if st not in field or model not in r: continue
        uids = list(field[st]); f = np.array([field[st][u] for u in uids], float); allv = np.append(f, r[model]); ok = allv > 0
        if not ok.any(): continue
        cap = np.percentile(allv[ok], 90); allv = np.where(ok, np.minimum(allv, cap), cap); allv = allv - allv.min()
        for u, v in zip(uids, allv[:-1]): num[u] += w * v; den[u] += w
        ours_num += w * allv[-1]; ours_den += w; n += 1
L_us = ours_num / ours_den; tot = ours_den
L_f = np.array([num[u] / den[u] for u in num if den[u] >= 0.8 * tot])
wts = np.exp(-beta * np.append(L_f, L_us)); share = wts[-1] / wts.sum()
print(f"{model} {days}d over {sys.argv[4:]}: prompts {n} | weighted L us {L_us:.2f} vs field median {np.median(L_f):.2f} (best {L_f.min():.2f}) | "
      f"share {share * 100:.3f}% vs median UID {np.median(wts[:-1]) / wts.sum() * 100:.3f}% | rank {int((L_f < L_us).sum()) + 1} of {len(L_f) + 1}")
