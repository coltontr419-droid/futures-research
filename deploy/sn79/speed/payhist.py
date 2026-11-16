"""252's score/skill/net alpha and field-wide skill totals over the last 30 h (validator 5EWwdZB7 gauges), every 3 h."""
import json, urllib.request, urllib.parse, time
P = "https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query"
def q(expr, t):
    u = P + "?" + urllib.parse.urlencode({"query": expr, "time": t})
    try: r = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "curl/8.5.0"}), timeout=30))["data"]["result"]
    except Exception as e: return None
    return r
W = 'wallet=~"5EWwdZB7.*"'
now = int(time.time())
print("CT time   | 252 score  skill  netα   kept | field: miners skill>0  Σskill  Σ netα(>0) | 252 share of Σskill | Σscore")
for h in range(30, -1, -3):
    t = now - h * 3600
    def one(g, a="252"):
        r = q(f'max(miner_gauges{{miner_gauge_name="{g}",agent_id="{a}",{W}}})', t); return float(r[0]["value"][1]) if r else float("nan")
    def field(g):
        r = q(f'max by (agent_id) (miner_gauges{{miner_gauge_name="{g}",{W}}})', t); return [float(x["value"][1]) for x in r] if r else []
    sk = field("debeta_skill"); na = field("debeta_skill_net_alpha"); sc = field("score")
    s252 = one("debeta_skill")
    print(f"{time.strftime('%m-%d %H:%M', time.gmtime(t - 6*3600))} | {one('score'):.4f} {s252:5.2f} {one('debeta_skill_net_alpha'):6.0f} {one('debeta_skill_books_kept'):4.0f} | {sum(1 for x in sk if x > 0):4d} {sum(x for x in sk if x > 0):7.1f} {sum(x for x in na if x > 0):9.0f} | {s252 / max(sum(x for x in sk if x > 0), 1e-9):6.2%} | {sum(sc):.3f}")
