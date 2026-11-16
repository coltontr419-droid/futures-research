import json, urllib.request, urllib.parse, time
P = "https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query"
def q(expr, t):
    u = P + "?" + urllib.parse.urlencode({"query": expr, "time": t})
    try: return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "curl/8.5.0"}), timeout=30))["data"]["result"]
    except Exception: return []
W = 'wallet=~"5EWwdZB7.*"'; now = int(time.time())
print("CT time     | 252 comb | field: n comb>0  Σcomb  median  top10 | 252 share | 216 comb | 252 skill-score rank")
for h in range(30, -1, -3):
    t = now - h * 3600
    d = {x["metric"]["agent_id"]: float(x["value"][1]) for x in q('max by (agent_id) (miner_gauges{miner_gauge_name="combined_score",' + W + '})', t)}
    pos = sorted([v for v in d.values() if v > 0], reverse=True); s = sum(pos)
    rk = 1 + sum(1 for v in pos if v > d.get("252", 0))
    print(f"{time.strftime('%m-%d %H:%M', time.gmtime(t - 6*3600))} | {d.get('252', float('nan')):.3f} | {len(pos):4d} {s:7.1f} {pos[len(pos)//2] if pos else 0:.3f} {sum(pos[:10]):6.2f} | {d.get('252',0)/max(s,1e-9):6.2%} | {d.get('216', float('nan')):.3f} | {rk}")
