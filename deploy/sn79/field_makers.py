import json
K = ["debeta_making", "debeta_notional", "debeta_coverage_books", "debeta_maker_notional_two_sided", "debeta_making_captured",
     "debeta_making_realized", "debeta_making_rank", "debeta_skill", "debeta_skill_books_kept", "combined_score"]
G = {}
for g in K:
    d = {}
    try:
        for r in json.load(open(f"/tmp/f_{g}.json"))["data"]["result"]:
            a = int(r["metric"].get("agent_id", -1)); d[a] = max(d.get(a, -1e18), float(r["value"][1]))
    except Exception:
        pass
    G[g] = d
top = sorted(G["debeta_making"], key=lambda u: -G["debeta_making"][u])[:12]
print(" uid  making rank  notional  mk2side books captured realized cred/$M  skill skbk combined")
for u in top + [213, 247]:
    g = lambda k: G[k].get(u, float("nan"))
    print(f"{u:4d} {g('debeta_making'):7.0f} {g('debeta_making_rank'):4.2f} {g('debeta_notional')/1e6:7.2f}M {g('debeta_maker_notional_two_sided')/1e6:6.2f}M "
          f"{g('debeta_coverage_books'):5.0f} {g('debeta_making_captured'):8.0f} {g('debeta_making_realized'):8.0f} "
          f"{g('debeta_making')/max(g('debeta_notional'), 1)*1e6:7.1f} {g('debeta_skill'):6.2f} {g('debeta_skill_books_kept'):4.0f} {g('combined_score'):6.3f}")
