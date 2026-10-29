# A132 (decisions.md 1107): 100K Fast Track on MGC full (18:00-16:55 ET) and evening sessions, and correlation with the MNQ slots. Run: python scripts/a132_mgc_full_session.py
import itertools, numpy as np, futuresres.reporting.a08_gold as a8
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a123_fast_track_policy import simulate
from futuresres.reporting.a124_fast_track_sizes import SIZES
T=dict(TERMS,**SIZES["100K"])
for win in ("full_1800_1655","eve_2100_1655"):
    E={e:a8.era_paths(e,"MGC",win)[:3] for e in ("pre","post")}
    for side in (1,-1):
        res={}
        for e,(h,l,c) in E.items():
            H,L,C=(h,l,c) if side>0 else (-l,-h,-c)
            res[e]={(w,lf):simulate(H,L,C,w*4000,lf*4000,0,None,T) for w,lf in itertools.product([0.15,0.2,0.325],[0.75,1.0])}
        o=[]
        for sel,oth in (("pre","post"),("post","pre")):
            b=max(res[sel],key=lambda k:res[sel][k][0]); o.append(f"chosen {sel} {b} -> {oth} {res[oth][b][0]:+7,.0f} ({res[oth][b][1]:.1f}/payout)")
        print(f"MGC {win:15} {'long' if side>0 else 'short':5} | "+" | ".join(o),flush=True)
# correlation of fresh-window outcomes: MGC full long vs MNQ full long vs MNQ rth long
W={}
for nm,(p,w) in {"MGC full":("MGC","full_1800_1655"),"MNQ full":("MNQ","full_1800_1655"),"MNQ rth":("MNQ","rth_0930_1600")}.items():
    for e in ("pre","post"):
        h,l,c,d=a8.era_paths(e,p,w)
        W[(nm,e)]={str(d[s]):simulate(h[s:s+84],l[s:s+84],c[s:s+84],800,4000,0,None,T)[0] for s in range(0,len(c)-84,3)}
for e in ("pre","post"):
    for a,b in (("MGC full","MNQ full"),("MGC full","MNQ rth")):
        k=sorted(set(W[(a,e)])&set(W[(b,e)])); x=np.array([W[(a,e)][i] for i in k]); y=np.array([W[(b,e)][i] for i in k])
        print(e,a,"vs",b,"n",len(k),"corr",round(np.corrcoef(x,y)[0,1],2),"P(both<0)",round(np.mean((x<0)&(y<0)),3), "MGC full mean",round(x.mean()),"P>0",round(np.mean(x>0),2))
