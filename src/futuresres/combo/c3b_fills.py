import json,os,sys,time,datetime as dt,collections
sys.path.insert(0,'kalshi_lip'); os.environ.setdefault("KALSHI_RATE","6")
from kalshi_api import Client
c=Client(); S=json.load(open('data/kalshi/rfq_shadow/c3_sample.json'))
def T(s): return dt.datetime.fromisoformat(s.replace('Z','+00:00'))
out=[]; cats=collections.Counter()
for k,o in enumerate(S):
    t0=T(o['created']) if isinstance(o['created'],str) else dt.datetime.fromtimestamp(o['created']/1000 if o['created']>1e11 else o['created'],dt.timezone.utc)
    lo=int(t0.timestamp()); hi=lo+30
    for a in range(5):
        try: d=c.req("GET",f"/markets/trades?ticker={o['ticker']}&min_ts={lo}&max_ts={hi}&limit=100"); break
        except Exception: time.sleep(3*(a+1)); d={}
    tr=d.get('trades',[])
    legs=o['sel'] or []; kinds=sorted({l['event_ticker'].split('-')[0] for l in legs})
    cat='crypto15m' if all('15M' in x for x in kinds) else ('mixed-crypto' if any('15M' in x for x in kinds) else 'sports/other')
    cats[cat]+=1
    o.update(fill=[{"p":float(x['yes_price_dollars']),"q":float(x['count_fp']),"side":x.get('taker_side')} for x in tr], cat=cat, t0=t0.isoformat())
    out.append(o)
    if k%300==0: print(k, flush=True)
json.dump(out,open('data/kalshi/rfq_shadow/c3_fills.json','w'))
filled=[o for o in out if o['fill']]
print('category counts', dict(cats))
print(f"RFQs with a trade on their combo within 30 s: {len(filled)}/{len(out)} ({len(filled)/len(out):.1%})")
for cat in cats:
    f=[o for o in filled if o['cat']==cat]; print(f"  {cat}: filled {len(f)}/{cats[cat]}; contracts {sum(x['q'] for o in f for x in o['fill']):,.0f}")
