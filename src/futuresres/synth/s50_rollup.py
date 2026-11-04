"""SN50 forward-test roll-up (decisions.md §1222): pools every archived forward day (data/synth/forward/<date>/) per competition, rebuilds the
validator's competition score per model over ALL those prompts (cap at the 90th percentile, minus the best, asset-weighted average, softmax
beta), and turns the share into $/month per UID from the competition's pool (miner pay / 3).
    python -m futuresres.synth.s50_rollup <miner pay $/month> [first date]"""
import json, sys
from pathlib import Path
import numpy as np
from futuresres.synth.s50_backtest import CACHE
W = {"SP500": 3.437935601155441, "AAPLX": 2.0916380815843123, "XAU": 1.7370922597118699, "GOOGLX": 1.6827392777257926, "TSLAX": 1.6068755936957768,
     "NVDAX": 1.6028217601617174, "WTIOIL": 0.8475062847978935, "SPCX": 0.4329342627683478, "BTC": 1.0, "ETH": 0.7064366394033871,
     "SOL": 0.6310037175639559, "XRP": 0.5658394110809131, "HYPE": 0.4784547133706857}
COMP = {"crypto-1h": ("1h", ["BTC", "ETH", "SOL", "XRP", "HYPE"], 0.3), "crypto-24h": ("24", ["BTC", "ETH", "SOL", "XRP", "HYPE"], 0.15),
        "com/equ-24h": ("24", ["SP500", "AAPLX", "XAU", "GOOGLX", "TSLAX", "NVDAX", "WTIOIL", "SPCX"], 0.15)}
pay, first = float(sys.argv[1]), (sys.argv[2] if len(sys.argv) > 2 else "")
days = sorted(d for d in (CACHE / "forward").iterdir() if d.is_dir() and d.name >= first)
print("folders ending -backfill are IN-SAMPLE (models were chosen on those prompts); the rest are true forward days")
print(f"forward days: {[d.name for d in days]} | competition pool ≈ ${pay / 3:,.0f}/month each")
total = {}
for comp, (tag, assets, beta) in COMP.items():
    num, den, models, n = {}, {}, None, 0
    ours, seen = {}, set()                                   # (asset, prompt, model) counted once: the backfill overlaps the first forward day
    for d in days:
        for a in assets:
            fs, fr = d / f"scores{tag}_{a}.json", d / f"rows{tag}_{a}.json"
            if not fs.exists() or not fr.exists(): continue
            field = json.loads(fs.read_text()); rows = json.loads(fr.read_text())
            for r in rows:
                st = r["start"]
                if st not in field: continue
                ms = [k for k in r if not k.startswith("_") and k != "start"]
                uids = list(field[st]); f = np.array([field[st][u] for u in uids], float)
                for m in ms:
                    if (a, st, m) in seen: continue
                    seen.add((a, st, m)); allv = np.append(f, r[m]); ok = allv > 0
                    if not ok.any(): continue
                    cap = np.percentile(allv[ok], 90); allv = np.where(ok, np.minimum(allv, cap), cap); allv = allv - allv.min()
                    o = ours.setdefault(m, [0.0, 0.0, {}, {}])
                    o[0] += W[a] * allv[-1]; o[1] += W[a]
                    for u, v in zip(uids, allv[:-1]): o[2][u] = o[2].get(u, 0.0) + W[a] * v; o[3][u] = o[3].get(u, 0.0) + W[a]
                n += 1
    print(f"\n{comp} ({n} prompt-asset rows):")
    best = 0.0
    for m, (on, od, fn, fd) in sorted(ours.items()):
        L_us = on / od; L_f = np.array([fn[u] / fd[u] for u in fn if fd[u] >= 0.8 * od])
        w = np.exp(-beta * np.append(L_f, L_us)); share = w[-1] / w.sum(); med = np.median(w[:-1]) / w.sum()
        usd = share * pay / 3; best = max(best, usd)
        print(f"  {m:46} share {share * 100:6.3f}% vs median UID {med * 100:5.3f}% | rank {int((L_f < L_us).sum()) + 1}/{len(L_f) + 1} | ≈ ${usd:6.0f}/month")
    total[comp] = best
print(f"\nbest variant per competition: " + ", ".join(f"{k} ${v:.0f}" for k, v in total.items()) + f" | ≈ ${sum(total.values()):.0f}/month per UID")
