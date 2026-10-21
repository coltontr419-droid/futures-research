# A106 (decisions.md 811): funded-bracket scaling (take, stop factors) under V2 payouts, 3 NKD + 2 FDXM, $116. No trial.
import datetime as dt, warnings, numpy as np
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import SEEDS, randomised, setup
from futuresres.reporting.a75_sim_contracts import LIVE
from futuresres.reporting.a85_account_lines import MIX
warnings.filterwarnings("ignore")
cp, Pp = data("post"); cq, Pq = data("pre"); P1, Q1 = launch_paths(Pp), launch_paths(Pq)
Fp, P = setup("50K", P1); Fq, Q = setup("50K", Q1); Fp.update(LIVE); Fq.update(LIVE)
st = np.array(cp[: len(cp) - 84]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st])
V2 = ("daily", 2100.0, 250.0, 1250.0)
for fs in (None, (1.25, 1.0), (1.5, 1.0), (1.0, 0.75), (1.25, 1.25), (0.75, 0.75)):
    Fa, Fb = dict(Fp, fee=116.0, payout=V2, fscale=fs), dict(Fq, fee=116.0, payout=V2, fscale=fs)
    r = f.simulate(cp, P, 84, MIX, Fa); rq = f.simulate(cq, Q, 84, MIX, Fb)
    a, b, c = summary(r, m25), summary(r, np.ones(len(st), bool)), summary(rq, np.ones(len(rq["net"]), bool))
    z = float(np.mean([f.simulate(cp, randomised(P, s), 84, MIX, Fa)["net"].mean() for s in SEEDS[:3]]))
    print(f"funded take x stop {str(fs or (1.0,1.0)):12}: 2025 {a['net_mean']:+8,.0f} ({a['p_pos']:.0%}, p10 {a['p10']:+,.0f}) | 2021-26 {b['net_mean']:+8,.0f} | 2010-20 {c['net_mean']:+8,.0f} | zero edge(3 seeds) {z:+,.0f}", flush=True)
