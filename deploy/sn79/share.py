import json, subprocess, numpy as np
def g(n):
    q = "miner_gauges{miner_gauge_name=\"%s\",wallet=~\"5EWwdZB7.*\"}" % n
    out = subprocess.run(["curl","-s","https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query","--data-urlencode","query="+q],capture_output=True,text=True).stdout
    return {int(r["metric"]["agent_id"]): float(r["value"][1]) for r in json.loads(out)["data"]["result"]}
mk, sh, sc, sk, cs, rk = g("debeta_making"), g("debeta_making_share"), g("score"), g("debeta_skill"), g("combined_score"), g("debeta_making_rank")
U = [u for u in mk if u != 0]
print("UIDs:", len(U), "| making > 0:", sum(1 for u in U if mk[u] > 0), "| making_share sum:", round(sum(sh.get(u, 0) for u in U), 3), "| score sum:", round(sum(sc.get(u, 0) for u in U), 3))
pos = sorted([u for u in U if mk[u] > 0], key=lambda u: mk[u])
for q in (0, .1, .25, .5, .75, .9, 1):
    u = pos[min(len(pos) - 1, int(q * (len(pos) - 1)))]
    print(f"  making p{int(q*100):3d}: uid {u:3d} making {mk[u]:7.1f} share {sh.get(u,0):.5f} rank {rk.get(u,0):.3f} skill {sk.get(u,0):+.3f} combined {cs.get(u,0):.3f} score {sc.get(u,0):.5f}")
z = [u for u in U if mk[u] == 0]
print(f"  making = 0: {len(z)} UIDs | share median {np.median([sh.get(u,0) for u in z]):.5f} | score median {np.median([sc.get(u,0) for u in z]):.5f} | skill>0: {sum(1 for u in z if sk.get(u,0) > 0)}")
x = np.array([mk[u] for u in pos]); y = np.array([sh[u] for u in pos])
for a in (1.0, 0.5, 0.25, 0.1):
    pred = x ** a; pred = pred / pred.sum() * y.sum(); r = np.corrcoef(pred, y)[0, 1]
    print(f"  share vs making^{a}: corr {r:.3f}")
print("  top score UIDs:", sorted([(round(sc[u], 5), u, round(mk.get(u,0)), round(sk.get(u,0), 2)) for u in U], reverse=True)[:6])
tot = sum(mk[u] for u in U)
for u in (64, 216, 52, 87, 7, 113, 138):
    print(f"  uid {u:3d}: share of CURRENT making {mk[u] / tot:.5f} vs published making_share {sh.get(u,0):.5f} (ratio {sh.get(u,0) / (mk[u] / tot):.2f}) | score {sc.get(u,0):.5f}")
mk_pool = sum(sc.get(u,0) for u in U if mk[u] > 0); sk_pool = sum(sc.get(u,0) for u in U if mk[u] == 0)
print(f"  pay split: makers (making > 0, n {len(pos)}) {mk_pool:.3f} of score, avg {mk_pool / len(pos):.5f} | non-makers (n {len(z)}) {sk_pool:.3f}, avg {sk_pool / len(z):.5f}")
