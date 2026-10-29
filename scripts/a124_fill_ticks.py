# §1099 addendum: 100K Fast Track with entries N ticks worse and takes needing M ticks through. Run: python scripts/a124_fill_ticks.py
import numpy as np, futuresres.reporting.a08_gold as a8
import futuresres.reporting.a123_fast_track_policy as m
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a124_fast_track_sizes import SIZES
T=dict(TERMS,**SIZES["100K"])
for prod,win,tick in (("MNQ","rth_0930_1600",0.5),("MNQ","full_1800_1655",0.5),("MGC","london_0300_1130",1.0)):
    for era in ("pre","post"):
        h,l,c=a8.era_paths(era,prod,win)[:3]
        row=[]
        for ent,thr in ((0,0),(1,1),(2,1),(3,2)):
            # entry ent ticks worse: path shifted down by ent*tick per contract; take must trade thr ticks through
            hh=h-ent*tick-thr*tick; ll=l-ent*tick; cc=c-ent*tick
            v,pp=m.simulate(hh,ll,cc,800,4000,0,None,T); row.append(f"{ent}t/{thr}t {v:+6,.0f}")
        print(prod,win,era," | ".join(row),flush=True)
