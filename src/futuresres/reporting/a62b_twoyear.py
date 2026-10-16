"""A62b - the build-up variants over two years (504 sessions, 2021-24 starts) (decisions.md 629). No trial."""
import warnings, numpy as np, json
warnings.filterwarnings("ignore")
from futuresres.reporting.a60_live import data
from futuresres.reporting.a62_buildlive import one, read
cp, Pp = data("post"); out = {}
for sz, cu in (((1200, 1000), 2000.0), ((1200, 1000), 10000.0), ((1200, 1000), 20000.0), ((800, 800), 20000.0), ((1200, 1000), 40000.0)):
    r, _ = one(cp, Pp, 504, live_pre=sz, live_post=sz, cushion=cu); x = read(r, np.ones(len(r["net"]), bool))
    out[f"{sz}|{cu}"] = x
    print(f"504 sessions, live {sz} cushion ${cu:,.0f}: cash {x['net_mean']:+,.0f} (P>0 {x['p_pos']:.0%}, p10 {x['p10']:+,.0f}) + live equity {x['live_eq_end']:,.0f} = {x['net_mean'] + x['live_eq_end']:+,.0f} | live paid {x['paid_live']:,.0f}, sim paid {x['paid_sim']:,.0f}, moves {x['moves']:.1f}, cool-off days {x['cool_days']:.0f}", flush=True)
json.dump(out, open("reports/a62b_twoyear.json", "w"), indent=1)
