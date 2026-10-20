import numpy as np, warnings, json
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data
from futuresres.reporting.a73_100k_live import SEEDS, randomised
warnings.filterwarnings("ignore")
cp, Pp = data("post")
cfg = {"Tradeify Select Daily": (116.0, "5: 3NKD+2FDXM"), "Lucid Daily": (129.5, "5: no Eurex (NKD×3, MNQ, MGC)")}
lows = {}; nets = {}
for firm, (fee, mix) in cfg.items():
    F = dict(f.FIRMS[firm], fee=fee); L = []; N = []
    for s in SEEDS[:3]:
        r = f.simulate(cp, randomised(Pp, s), 84, f.MIXES[mix], F); L.append(r["min_cash"]); N.append(r["net"])
    lows[firm] = np.concatenate(L); nets[firm] = np.concatenate(N)
    lo = lows[firm]
    print(f"{firm:22}: zero-edge net mean {nets[firm].mean():+,.0f}, P(net>0) {(nets[firm]>0).mean():.0%} | cash low median {np.median(lo):+,.0f}, 5% {np.percentile(lo,5):+,.0f}, worst {lo.min():+,.0f}")
both = lows["Tradeify Select Daily"] + lows["Lucid Daily"]; nb = nets["Tradeify Select Daily"] + nets["Lucid Daily"]
print(f"both (sum of each run's low; conservative): cash low median {np.median(both):+,.0f}, 5% {np.percentile(both,5):+,.0f}, worst {both.min():+,.0f} | combined net mean {nb.mean():+,.0f}, P(>0) {(nb>0).mean():.0%}, p10 {np.percentile(nb,10):+,.0f}")
