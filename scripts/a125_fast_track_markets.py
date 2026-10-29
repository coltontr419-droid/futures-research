# A125 (decisions.md 1099): Bulenox Fast Track 100K on other markets/sessions — fresh 84-session windows and cross-slot correlation. Run: python scripts/a125_fast_track_markets.py
import numpy as np, futuresres.reporting.a08_gold as a8
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a123_fast_track_policy import simulate
from futuresres.reporting.a124_fast_track_sizes import SIZES
T=dict(TERMS,**SIZES["100K"])
cfg={"MNQ rth long":("MNQ","rth_0930_1600",1),"MNQ full long":("MNQ","full_1800_1655",1),"MGC london long":("MGC","london_0300_1130",1),"MGC london short":("MGC","london_0300_1130",-1)}
W={}
for name,(p,w,side) in cfg.items():
    for era in ("pre","post"):
        h,l,c,d=a8.era_paths(era,p,w)
        H,L,C=(h,l,c) if side>0 else (-l,-h,-c)
        vals={}
        for st in range(0,len(c)-84,3):
            v,_=simulate(H[st:st+84],L[st:st+84],C[st:st+84],800,4000,0,None,T); vals[str(d[st])]=v
        W[(name,era)]=vals
        v=np.array(list(vals.values()))
        print(f"{name:16} {era:4} mean {v.mean():+7,.0f} P>0 {np.mean(v>0):.0%} p10 {np.percentile(v,10):+7,.0f} worst {v.min():+7,.0f}",flush=True)
# correlation of window outcomes by matching start dates
for era in ("pre","post"):
    a=W[("MNQ rth long",era)]; b=W[("MGC london long",era)]; f=W[("MNQ full long",era)]
    k=sorted(set(a)&set(b)); 
    if len(k)>20:
        x=np.array([a[i] for i in k]); y=np.array([b[i] for i in k])
        print(era,"windows",len(k),"corr MNQrth vs MGC",round(np.corrcoef(x,y)[0,1],2),"| P(both<0)",round(np.mean((x<0)&(y<0)),3),"P(MNQ<0)",round(np.mean(x<0),3))
    k2=sorted(set(a)&set(f))
    x=np.array([a[i] for i in k2]); z=np.array([f[i] for i in k2]); print(era,"corr MNQrth vs MNQfull",round(np.corrcoef(x,z)[0,1],2))
