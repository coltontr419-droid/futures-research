import json,os,sys,math,time,statistics as st
sys.path.insert(0,'kalshi_lip'); os.environ["KALSHI_RATE"]="2"
from kalshi_api import Client
c=Client(); S=json.load(open('data/kalshi/rfq_shadow/c3_fills.json'))
def fee(p): return math.ceil(7*p*(1-p))/100
rows=[]
for o in S:
    sel=o['sel'] or []; games=[l['event_ticker'].split('-',1)[1] if '-' in l['event_ticker'] else l['event_ticker'] for l in sel]
    if len(set(games))==len(games) or not o['fill']: continue
    mids=[]
    for l in sel:
        b=o['legs'].get(l['market_ticker']) or {}; yb,ya=b.get('yes_bid'),b.get('yes_ask')
        if yb is None or ya is None or ya-yb>0.10 or not (0.03<=(yb+ya)/2<=0.97): mids=None; break
        m=(yb+ya)/2; mids.append(m if l['side']=='yes' else 1-m)
    if not mids: continue
    yes=[x for x in o['fill'] if x['side']=='yes']
    if not yes: continue
    px=sum(x['p']*x['q'] for x in yes)/sum(x['q'] for x in yes)
    rows.append({"ticker":o['ticker'],"indep":math.prod(mids),"exec":px,"q":sum(x['q'] for x in yes),"crypto":any('15M' in l['event_ticker'] for l in sel)})
for r in rows:
    m=None
    for a in range(6):
        try: m=c.req("GET",f"/markets/{r['ticker']}")['market']; break
        except Exception: time.sleep(5*(a+1))
    r['result']=m.get('result') if m else None
json.dump(rows,open('data/kalshi/rfq_shadow/c3_samegame.json','w'))
for lab,sub in (("sports same-game",[r for r in rows if not r['crypto']]),("crypto same-window",[r for r in rows if r['crypto']])):
    if not sub: continue
    print(f"{lab}: YES-filled {len(sub)}; executed / independent product: median {st.median(r['exec']/r['indep'] for r in sub):.2f}")
    sett=[r for r in sub if r['result'] in ('yes','no')]
    if sett:
        V=sum(r['q'] for r in sett); y=sum(r['q']*(r['result']=='yes') for r in sett)/V
        print(f"   settled {len(sett)}: YES rate {y:.3f} | executed {sum(r['q']*r['exec'] for r in sett)/V:.3f} | independent {sum(r['q']*r['indep'] for r in sett)/V:.3f} | "
              f"buyers' P&L ${sum(r['q']*((r['result']=='yes')-r['exec']-fee(r['exec'])) for r in sett):,.0f} on ${sum(r['q']*r['exec'] for r in sett):,.0f}; "
              f"combos won by buyers {sum(r['result']=='yes' for r in sett)}/{len(sett)}")
