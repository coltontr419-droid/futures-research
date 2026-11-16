import json, subprocess, sys, time, statistics as st
P = "https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query_range"
end = int(time.time()); start = end - 8 * 3600; step = 1800
def q(expr):
    out = subprocess.run(["curl", "-s", "-m", "40", "-G", P, "--data-urlencode", f"query={expr}", "--data-urlencode", f"start={start}", "--data-urlencode", f"end={end}",
                          "--data-urlencode", f"step={step}"], capture_output=True, text=True).stdout
    try: return json.loads(out)["data"]["result"]
    except Exception: print("ERR", out[:200]); return []
W = 'wallet=~"5EWwdZB7.*"'
series = {}
for name, expr in [("255 skill", 'max(miner_gauges{miner_gauge_name="debeta_skill",agent_id="255",' + W + '})'),
                   ("255 net alpha", 'max(miner_gauges{miner_gauge_name="debeta_skill_net_alpha",agent_id="255",' + W + '})'),
                   ("255 scored books", 'max(miner_gauges{miner_gauge_name="num_scored_books",agent_id="255",' + W + '})'),
                   ("255 score", 'max(miner_gauges{miner_gauge_name="score",agent_id="255",' + W + '})'),
                   ("252 skill", f'max(miner_gauges{{miner_gauge_name="debeta_skill",agent_id="252",{W}}})'),
                   ("252 net alpha", f'max(miner_gauges{{miner_gauge_name="debeta_skill_net_alpha",agent_id="252",{W}}})'),]:
    r = q(expr); series[name] = {int(t): float(v) for t, v in (r[0]["values"] if r else [])}
ts = sorted(set().union(*[set(v) for v in series.values()]))
print("CT hour   " + " | ".join(f"{n:>22}" for n in series))
for t in ts:
    h = time.strftime("%m-%d %H:%M", time.gmtime(t - 6 * 3600))
    print(f"{h} " + " | ".join(f"{series[n].get(t, float('nan')):22.2f}" for n in series))
