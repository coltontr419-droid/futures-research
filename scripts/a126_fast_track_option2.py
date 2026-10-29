# A126 (decisions.md 1100): Fast Track Option 2 (EOD drawdown + daily loss limit) by size and market, minute paths. Run: python scripts/a126_fast_track_option2.py
import itertools, numpy as np, futuresres.reporting.a08_gold as a8
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a124_fast_track_sizes import SIZES
RT=2.32
def trade_eod(h,l,c,W,L,n):
    cost=RT*n
    for j in range(len(c)):
        if l[j]<=-L: return -n*L-cost
        if h[j]>=W: return n*W-cost
    return n*float(c[-1])-cost
def sim(H,Lo,C,Wd,Ld,T):
    n=max(1,int(round(max(Wd,Ld)/600.))); W,L=Wd/n,Ld/n
    bal=pk=cyc=cbest=0.;npay=0;bought=1;paid=0.;pays=0
    for s in range(len(C)):
        x=trade_eod(H[s],Lo[s],C[s],W,L,n)
        bal+=x
        if bal<=min(pk-T["dd"],T["lock"]):
            bought+=1;bal=pk=cyc=cbest=0.;npay=0;continue
        pk=max(pk,bal);cyc+=x;cbest=max(cbest,x)
        goal=T["goal1"] if npay==0 else T["goalN"];cons=T["cons"][min(npay,2)]
        amt=min(bal-T["lock"]-1,T["caps"][min(npay,3)])
        if cyc>=goal and cbest<=cons*cyc and amt>=T["pmin"]:
            bal-=amt;npay+=1;pays+=1;paid+=amt*T["split"];cyc=cbest=0.
    return (paid-bought*T["fee"])/len(C)*84, bought/max(pays,1)
for prod,win in (("MNQ","rth_0930_1600"),("MNQ","full_1800_1655"),("MGC","london_0300_1130")):
    E={e:a8.era_paths(e,prod,win)[:3] for e in ("pre","post")}
    for size,dll in (("50K",1200.),("100K",2500.),("150K",3300.)):
        T=dict(TERMS,**SIZES[size])
        grid=[(w,lf) for w,lf in itertools.product([0.1,0.2,0.325,0.45],[0.25,0.5,0.75,1.0]) if lf*T["dd"]<=dll]
        res={e:{k:sim(*E[e],k[0]*T["dd"],k[1]*T["dd"],T) for k in grid} for e in E}
        for sel,oth in (("pre","post"),("post","pre")):
            b=max(res[sel],key=lambda k:res[sel][k][0])
            print(f"Opt2 {prod} {win:16} {size:5} chosen on {sel} {b}: {sel} {res[sel][b][0]:+7,.0f} | {oth} {res[oth][b][0]:+7,.0f} ({res[oth][b][1]:.1f}/payout)",flush=True)
