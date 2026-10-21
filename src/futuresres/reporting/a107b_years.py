import warnings, numpy as np, collections
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import setup
from futuresres.reporting.a75_sim_contracts import LIVE
from futuresres.reporting.a85_account_lines import MIX
warnings.filterwarnings("ignore")
cp, Pp = data("post"); cq, Pq = data("pre"); Fp, P = setup("50K", launch_paths(Pp)); Fq, Q = setup("50K", launch_paths(Pq)); Fp.update(LIVE); Fq.update(LIVE)
V2 = ("daily", 2100.0, 250.0, 1250.0)
for nm, (c_, P_, F_) in {"2021-26": (cp, P, Fp), "2010-20": (cq, Q, Fq)}.items():
    st = np.array(c_[: len(c_) - 84]); yrs = np.array([x.year for x in st])
    res = {}
    for fs in (None, (1.0, 0.75)):
        res[fs] = f.simulate(c_, P_, 84, MIX, dict(F_, fee=116.0, payout=V2, fscale=fs))["net"]
    for y in sorted(set(yrs)):
        m = yrs == y; a = res[None][m].mean(); b = res[(1.0, 0.75)][m].mean()
        print(f"{nm} {y}: 1x {a:+8,.0f}  0.75x {b:+8,.0f}  diff {b-a:+7,.0f}", flush=True)
