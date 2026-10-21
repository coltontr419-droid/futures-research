import datetime as dt, warnings, numpy as np
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import setup
from futuresres.reporting.a75_sim_contracts import LIVE
from futuresres.reporting.a85_account_lines import MIX
warnings.filterwarnings("ignore")
cp, Pp = data("post"); cq, Pq = data("pre"); Fp, P = setup("50K", launch_paths(Pp)); Fq, Q = setup("50K", launch_paths(Pq)); Fp.update(LIVE); Fq.update(LIVE)
st = np.array(cp[: len(cp) - 84]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st])
V2 = ("daily", 2100.0, 250.0, 1250.0)
for k in (0.6, 0.7, 0.75, 0.8, 0.9, 1.0):
    Fa, Fb = dict(Fp, fee=116.0, payout=V2, fscale=(1.0, k)), dict(Fq, fee=116.0, payout=V2, fscale=(1.0, k))
    r = f.simulate(cp, P, 84, MIX, Fa); rq = f.simulate(cq, Q, 84, MIX, Fb)
    a, b, c = summary(r, m25), summary(r, np.ones(len(st), bool)), summary(rq, np.ones(len(rq["net"]), bool))
    print(f"funded stop {k:.2f}x: 2025 {a['net_mean']:+8,.0f} ({a['p_pos']:.0%}) | 2021-26 {b['net_mean']:+8,.0f} | 2010-20 {c['net_mean']:+8,.0f}", flush=True)
