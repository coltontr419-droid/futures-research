import futuresres.reporting.a08_gold as a8
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a123_fast_track_policy import simulate
from futuresres.reporting.a124_fast_track_sizes import SIZES
E={era:a8.era_paths(era,"MNQ","rth_0930_1600")[:3] for era in ("pre","post")}
base=dict(TERMS,**SIZES["100K"])
vars_={"base (caps 2.5k/3k, later goal 3k)":{},
 "caps 2k/2.5k":dict(caps=(2000.,2000.,2000.,2500.)),
 "caps 3k/3.5k":dict(caps=(3000.,3000.,3000.,3500.)),
 "later goal 6k":dict(goalN=6000.),
 "consistency 30% flat":dict(cons=(0.30,)),
 "list price $648":dict(fee=648.),
 "drawdown 3k (like Qualification)":dict(dd=3000.),
 "caps 2k + later goal 6k + list price":dict(caps=(2000.,2000.,2000.,2500.),goalN=6000.,fee=648.)}
for k,v in vars_.items():
    T=dict(base,**v); L=T["dd"]
    r=[simulate(*E[e],0.2*L,L,0,None,T) for e in ("pre","post")]
    print(f"{k:40} pre {r[0][0]:+7,.0f} ({r[0][1]:.1f}/payout)  post {r[1][0]:+7,.0f} ({r[1][1]:.1f})",flush=True)
