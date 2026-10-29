# §1099 addendum 3: Fast Track size choice on MNQ full session and MGC London (era-swapped). Run: python scripts/a131_sizes_by_market.py
import itertools, futuresres.reporting.a08_gold as a8
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a123_fast_track_policy import simulate
from futuresres.reporting.a124_fast_track_sizes import SIZES
for prod,win in (("MNQ","full_1800_1655"),("MGC","london_0300_1130")):
    E={e:a8.era_paths(e,prod,win)[:3] for e in ("pre","post")}
    for name,s in SIZES.items():
        T=dict(TERMS,**s)
        res={e:{(w,l):simulate(*E[e],w*s["dd"],l*s["dd"],0,None,T) for w,l in itertools.product([0.15,0.2,0.325],[0.75,1.0])} for e in E}
        o=[]
        for sel,oth in (("pre","post"),("post","pre")):
            b=max(res[sel],key=lambda k:res[sel][k][0]); o.append(f"chosen {sel} {b} -> {oth} {res[oth][b][0]:+7,.0f} ({res[oth][b][1]:.1f}/payout, {res[oth][b][0]/T['fee']:.1f}x fee)")
        print(f"{prod} {win:16} {name:5} | "+" | ".join(o),flush=True)
