import warnings, numpy as np
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import SEEDS, randomised, setup
from futuresres.reporting.a75_sim_contracts import LIVE
from futuresres.reporting.a85_account_lines import MIX
warnings.filterwarnings("ignore")
cp, Pp = data("post"); cq, Pq = data("pre"); Fp, P = setup("50K", launch_paths(Pp)); Fq, Q = setup("50K", launch_paths(Pq)); Fp.update(LIVE); Fq.update(LIVE)
V2 = ("daily", 2100.0, 250.0, 1250.0)
for k in (1.0, 0.7):
    Fa, Fb = dict(Fp, fee=116.0, payout=V2, fscale=(1.0, k)), dict(Fq, fee=116.0, payout=V2, fscale=(1.0, k))
    z1 = np.mean([f.simulate(cp, randomised(P, s), 84, MIX, Fa)["net"].mean() for s in SEEDS])
    z2 = np.mean([f.simulate(cq, randomised(Q, s), 84, MIX, Fb)["net"].mean() for s in SEEDS])
    print(f"funded stop {k:.1f}x zero edge 2021-26 {z1:+,.0f} / 2010-20 {z2:+,.0f}", flush=True)
