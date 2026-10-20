import json,os,sys,math,time,collections,statistics as st
sys.path.insert(0,'kalshi_lip'); os.environ.setdefault("KALSHI_RATE","6")
from kalshi_api import Client
c=Client(); S=json.load(open('data/kalshi/rfq_shadow/c3_fills.json'))
def fee(p): return math.ceil(7*p*(1-p))/100
rows=[]
for o in S:
    if o['cat']!='sports/other' or not o['fill']: continue
    sel=o['sel'] or []; games=[l['event_ticker'].split('-',1)[1] if '-' in l['event_ticker'] else l['event_ticker'] for l in sel]
    if len(set(games))<len(games): continue                     # same-game legs: correlated, excluded
    mids=[]
    for l in sel:
        b=o['legs'].get(l['market_ticker']) or {}; yb,ya=b.get('yes_bid'),b.get('yes_ask')
        if yb is None or ya is None or ya-yb>0.10 or not (0.05<=(yb+ya)/2<=0.95): mids=None; break
        m=(yb+ya)/2; mids.append(m if l['side']=='yes' else 1-m)
    if not mids: continue
    fair=math.prod(mids)
    yes=[x for x in o['fill'] if x['side']=='yes']
    if not yes: continue
    px=sum(x['p']*x['q'] for x in yes)/sum(x['q'] for x in yes); q=sum(x['q'] for x in yes)
    rows.append({"ticker":o['ticker'],"fair":fair,"exec":px,"q":q,"legs":len(mids)})
# settlement
for r in rows:
    for a in range(4):
        try: m=c.req("GET",f"/markets/{r['ticker']}")['market']; break
        except Exception: time.sleep(3)
    r['result']=m.get('result') if m else None
json.dump(rows,open('data/kalshi/rfq_shadow/c3_priced.json','w'))
print('independent pre-game sports combos with a YES fill:', len(rows))
print('markup exec/fair: median %.2f, quartiles %.2f / %.2f' % (st.median(r['exec']/r['fair'] for r in rows), sorted(r['exec']/r['fair'] for r in rows)[len(rows)//4], sorted(r['exec']/r['fair'] for r in rows)[3*len(rows)//4]))
sett=[r for r in rows if r['result'] in ('yes','no')]
if sett:
    V=sum(r['q'] for r in sett); y=sum(r['q']*(r['result']=='yes') for r in sett)/V
    print(f"settled {len(sett)}: contract-weighted YES rate {y:.3f} vs fair {sum(r['q']*r['fair'] for r in sett)/V:.3f} vs executed {sum(r['q']*r['exec'] for r in sett)/V:.3f}")
    print(f"  incumbents' realised margin (sellers): ${sum(r['q']*(r['exec']-(r['result']=='yes')) for r in sett):,.0f} on ${sum(r['q']*r['exec'] for r in sett):,.0f} premium")
    for mu in (1.05,1.10,1.20,1.30):
        won=[(max(r['fair']*mu, r['fair']+0.01), r) for r in sett]; won=[(qq,r) for qq,r in won if qq<r['exec']]
        pnl=sum(r['q']*(qq-(r['result']=='yes')-0.01) for qq,r in won); prem=sum(r['q']*qq for qq,r in won)
        print(f"  quote YES at fair x{mu:.2f}: win {len(won)}/{len(sett)} combos, P&L ${pnl:,.0f} on ${prem:,.0f} premium ({pnl/max(prem,1):+.1%}); collateral-days ~${sum(r['q']*(1-qq) for qq,r in won):,.0f}")
