import warnings, numpy as np
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import setup
from futuresres.reporting.a75_sim_contracts import LIVE
from futuresres.reporting.a85_account_lines import MIX
warnings.filterwarnings("ignore")
cp, Pp = data("post"); Fp, P = setup("50K", launch_paths(Pp)); Fp.update(LIVE)
V2 = ("daily", 2100.0, 250.0, 1250.0)
st = np.array(cp[: len(cp) - 84])
for fs in ((0.9,0.7),(0.95,0.7),(1.0,0.7),(1.05,0.7),(1.0,1.0),(0.9,1.0)):
    r = f.simulate(cp, P, 84, MIX, dict(Fp, fee=116.0, payout=V2, fscale=fs)); b = summary(r, np.ones(len(st), bool))
    print(f"take x{fs[0]:.2f} stop x{fs[1]:.2f}: net {b['net_mean']:+8,.0f} | evals {b['evals']:.1f} fees ${b['fees']:,.0f} | funded paid ${b['paid_sim']:,.0f} | live paid ${b['paid_live']:,.0f} | moves to live {b['moves']:.2f}", flush=True)
