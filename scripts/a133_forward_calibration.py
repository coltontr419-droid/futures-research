# §1107 addendum: how unusual are the first forward months? Net over the first n sessions from a fresh start, history. Run: python scripts/a133_forward_calibration.py
import numpy as np, futuresres.reporting.a08_gold as a8
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a123_fast_track_policy import simulate
from futuresres.reporting.a124_fast_track_sizes import SIZES
T=dict(TERMS,**SIZES["100K"])
for nm,(p,w,n,obs) in {"MNQ rth":("MNQ","rth_0930_1600",21,-713),"MNQ full":("MNQ","full_1800_1655",16,-2138),"MGC london":("MGC","london_0300_1130",20,-2138),"MGC full":("MGC","full_1800_1655",16,-1782)}.items():
    v=[]
    for e in ("pre","post"):
        h,l,c=a8.era_paths(e,p,w)[:3]
        for s in range(0,len(c)-n,2):
            x,_=simulate(h[s:s+n],l[s:s+n],c[s:s+n],800,4000,0,None,T); v.append(x*n/84)
    v=np.array(v); print(f"{nm:10} first {n} sessions from a fresh start: mean {v.mean():+6,.0f}  P(net<0) {np.mean(v<0):.0%}  P(net <= observed {obs:+,}) {np.mean(v<=obs+1):.0%}",flush=True)
