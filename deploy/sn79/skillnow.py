"""§1395: who earns skill now, and is it new? Live gauges for all UIDs; compares with the morning paysplit classes (making-only list from fleets.py run ≈ 12:40 PM)."""
import json, subprocess, collections
P = "https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query"
def g(name):
    r = subprocess.run(["curl", "-s", "-G", P, "--data-urlencode", f'query=max by (agent_id) (miner_gauges{{miner_gauge_name="{name}"}})'], capture_output=True, text=True).stdout
    return {int(x["metric"]["agent_id"]): float(x["value"][1]) for x in json.loads(r)["data"]["result"] if x["metric"].get("agent_id", "").isdigit()}
mk, sk, kept = g("debeta_making"), g("debeta_skill"), g("debeta_skill_books_kept")
F = [7, 40, 52, 55, 87, 102, 110, 132, 166, 183, 216]
print("fleet 5F1F2JMu settled makers now (uid: making / skill / skill books kept):")
print("  " + " | ".join(f"{u}: {mk.get(u, 0):.0f}/{sk.get(u, 0):.2f}/{kept.get(u, 0):.0f}" for u in F))
mm = [u for u in mk if mk[u] > 100]
withsk = [u for u in mm if sk.get(u, 0) > 0]
print(f"UIDs with making > 100: {len(mm)}; of those with skill > 0 now: {len(withsk)}")
print("skill > 0 among them, sorted by skill:", sorted(((round(sk[u], 2), u, round(mk[u])) for u in withsk), reverse=True)[:25])
print("x3/x1:", {u: (round(mk.get(u, 0)), sk.get(u, 0), kept.get(u, 0)) for u in (64, 27)})
