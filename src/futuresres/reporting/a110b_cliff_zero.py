import warnings, numpy as np
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import SEEDS, randomised, setup
from futuresres.reporting.a75_sim_contracts import LIVE
from futuresres.reporting.a85_account_lines import MIX
warnings.filterwarnings("ignore")
cp, Pp = data("post"); Fp, P = setup("50K", launch_paths(Pp)); Fp.update(LIVE)
V2 = ("daily", 2100.0, 250.0, 1250.0)
for fs in ((1.0,1.0),(1.0,0.9),(1.0,0.8),(1.0,0.7),(1.0,0.6),(0.9,0.7),(0.95,0.7),(1.05,0.7)):
    z = [f.simulate(cp, randomised(P, s), 84, MIX, dict(Fp, fee=116.0, payout=V2, fscale=fs))["net"].mean() for s in SEEDS]
    print(f"take x{fs[0]:.2f} stop x{fs[1]:.2f}: zero edge mean {np.mean(z):+7,.0f}  seed range {min(z):+,.0f}..{max(z):+,.0f}", flush=True)
