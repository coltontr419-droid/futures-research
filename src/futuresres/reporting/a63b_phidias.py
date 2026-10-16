"""A63b - Phidias Fundamental and Premium 50K (5 and 15 accounts) in the A63 simulation (decisions.md 631). No trial."""
import numpy as np, datetime as dt, warnings, json; warnings.filterwarnings("ignore")
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary
cp,Pp=data("post"); cq,Pq=data("pre"); st=np.array(cp[:len(cp)-84]); m25=st>=dt.date(2025,1,1); out={}
for firm in ("Phidias Fundamental","Phidias Premium"):
    for mix in ("5: 3NKD+2FDXM","15: 9NKD+6FDXM"):
        F=f.FIRMS[firm]; r=f.simulate(cp,Pp,84,f.MIXES[mix],F); rq=f.simulate(cq,Pq,84,f.MIXES[mix],F)
        a,b,c=summary(r,m25),summary(r,np.ones(len(st),bool)),summary(rq,np.ones(len(rq["net"]),bool)); out[f"{firm} | {mix}"]={"2025 starts":a,"2021-26":b,"2010-20":c}
        print(f"{firm} | {mix}: 2025 {a['net_mean']:+,.0f} ({a['p_pos']:.0%}) | 2021-26 {b['net_mean']:+,.0f} ({b['p_pos']:.0%}, p10 {b['p10']:+,.0f}) | 2010-20 {c['net_mean']:+,.0f} ({c['p_pos']:.0%}) | fees {b['fees']:,.0f} paid {b['paid_sim']:,.0f}", flush=True)
json.dump(out,open("reports/a63_phidias.json","w"),indent=1,default=str)
