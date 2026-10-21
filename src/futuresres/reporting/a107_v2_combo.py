import datetime as dt, warnings, numpy as np
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import SEEDS, randomised, setup
from futuresres.reporting.a75_sim_contracts import LIVE
warnings.filterwarnings("ignore")
cp, Pp = data("post"); cq, Pq = data("pre"); P1, Q1 = launch_paths(Pp), launch_paths(Pq)
Fp, P = setup("50K", P1); Fq, Q = setup("50K", Q1); Fp.update(LIVE); Fq.update(LIVE)
st = np.array(cp[: len(cp) - 84]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st])
V2 = ("daily", 2100.0, 250.0, 1250.0)
for mx in ("5: 3NKD+2FDXM", "5: 2NKD+3FDXM"):
    for fs in (None, (1.0, 0.75)):
        M = f.MIXES[mx]; Fa, Fb = dict(Fp, fee=116.0, payout=V2, fscale=fs), dict(Fq, fee=116.0, payout=V2, fscale=fs)
        r = f.simulate(cp, P, 84, M, Fa); rq = f.simulate(cq, Q, 84, M, Fb)
        a, b, c = summary(r, m25), summary(r, np.ones(len(st), bool)), summary(rq, np.ones(len(rq["net"]), bool))
        z = float(np.mean([f.simulate(cp, randomised(P, s), 84, M, Fa)["net"].mean() for s in SEEDS]))
        print(f"{mx:15} stop {('0.75x' if fs else '1x'):5}: 2025 {a['net_mean']:+8,.0f} ({a['p_pos']:.0%}, p10 {a['p10']:+,.0f}) | 2021-26 {b['net_mean']:+8,.0f} ({b['p_pos']:.0%}) | 2010-20 {c['net_mean']:+8,.0f} ({c['p_pos']:.0%}) | zero edge {z:+,.0f}", flush=True)
