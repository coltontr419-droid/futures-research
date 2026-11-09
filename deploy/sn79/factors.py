import json, subprocess
U = ["64", "216", "87", "52", "241", "7"]
names = ["combined_score","debeta_score","debeta_making","debeta_making_basis","debeta_making_captured","debeta_making_realized","debeta_making_share","debeta_making_rank","debeta_w_make","debeta_weight","debeta_skill","debeta_skill_rank","debeta_p11_factor","debeta_s3_factor","debeta_conjunction","debeta_presence_share","debeta_coverage_books","debeta_bg_share","debeta_at_best_seconds","debeta_best_size","debeta_notional","debeta_maker_notional_two_sided","activity_factor","pnl_factor","trading_score","gentrx_score","unnormalized_score","score"]
for n in names:
    q = "miner_gauges{miner_gauge_name=\"%s\",wallet=~\"5EWwdZB7.*\"}" % n
    out = subprocess.run(["curl","-s","https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query","--data-urlencode","query="+q],capture_output=True,text=True).stdout
    try: d = {r["metric"]["agent_id"]: float(r["value"][1]) for r in json.loads(out)["data"]["result"]}
    except Exception: d = {}
    print(n.ljust(32), " | ".join(f"{u}: {d[u]:.4g}" if u in d else f"{u}: -" for u in U))
