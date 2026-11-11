"""§1380: the validator's own daily_volume gauge per book (rolling 24 sim h) for x3 vs the top makers."""
import json, subprocess
P = "https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query"
for u in (64, 48, 178, 119, 117, 5, 146, 216):
    q = f'max by (book_id) (agent_gauges{{agent_gauge_name="daily_volume",agent_id="{u}"}})'
    r = json.loads(subprocess.run(["curl", "-s", "-G", P, "--data-urlencode", "query=" + q], capture_output=True, text=True).stdout)["data"]["result"]
    v = sorted(float(x["value"][1]) for x in r)
    if not v: print(u, "no data"); continue
    print(f"UID {u:3d}: books {len(v)} | daily volume per book median ${v[len(v)//2]/1e3:.0f}k p90 ${v[int(.9*(len(v)-1))]/1e3:.0f}k max ${v[-1]/1e3:.0f}k | books ≥ $490k: {sum(x >= 490000 for x in v)}")
q = 'max(miner_gauges{miner_gauge_name="total_daily_volume",agent_id="48"})'
print("UID 48 total_daily_volume:", json.loads(subprocess.run(["curl", "-s", "-G", P, "--data-urlencode", "query=" + q], capture_output=True, text=True).stdout)["data"]["result"][0]["value"][1])
