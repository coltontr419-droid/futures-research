"""A102 (decisions.md 807): the one-NKD-account launch (A68) under V2 payouts vs the old model. No trial."""
import warnings, numpy as np
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import setup
from futuresres.reporting.a75_sim_contracts import LIVE
warnings.filterwarnings("ignore")
cp, Pp = data("post"); Fp, P = setup("50K", launch_paths(Pp)); Fp.update(LIVE)
for name, pay in {"old model": ("cap", 2000.0, 0.0, 1250.0), "V2": ("daily", 2100.0, 250.0, 1250.0)}.items():
    r = f.simulate(cp, P, 252, ("NKD",), dict(Fp, fee=116.0, payout=pay))
    d2 = r["pay2_day"]; ok = d2 >= 0
    q = np.percentile(d2[ok], [25, 50, 75, 90]) if ok.any() else []
    print(f"{name:9}: reached 2nd payout {ok.mean():.0%} within 252 sessions; sessions to it p25/median/p75/p90 {[int(x) for x in q]}; "
          f"cash low before it median {np.median(r['low_pay2'][ok]):+,.0f}, 95th pct {np.percentile(r['low_pay2'][ok],5):+,.0f}, worst {r['low_pay2'][ok].min():+,.0f}; "
          f"fees by then median {np.median(r['fees_pay2'][ok]):,.0f}")
