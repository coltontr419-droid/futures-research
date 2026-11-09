"""§1353: where x3's steady level would rank among all 256 UIDs — (1) live making gauge (validator 5EWwdZB7) vs x3's projected steady ≈ 335,
(2) chain emission vs x3's estimated steady pay. Also how many slots are filled by young (protected) UIDs.  python3 rankpos.py <steady making> <steady pay ratio vs line>"""
import json, subprocess, sys, numpy as np, bittensor as bt
SM, SR = float(sys.argv[1]), float(sys.argv[2])
q = 'miner_gauges{miner_gauge_name="debeta_making",wallet=~"5EWwdZB7.*"}'
out = subprocess.run(["curl", "-s", "https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query", "--data-urlencode", f"query={q}"], capture_output=True, text=True).stdout
mk = {int(r["metric"]["agent_id"]): float(r["value"][1]) for r in json.loads(out)["data"]["result"]}
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); blk = st.get_current_block()
imm = st.query_subtensor("ImmunityPeriod", params=[79]).value; E = np.array(m.emission, dtype=float)
rb = np.array([int(st.query_subtensor("BlockAtRegistration", params=[79, u]).value) for u in range(256)]); prot = (blk - rb) < imm
non = [u for u in range(1, 256) if not prot[u]]; line = min(E[u] for u in non)
fleet = {u for u in range(256) if m.coldkeys[u].startswith("5F1F2JMu")}
vals = np.array([mk.get(u, 0.0) for u in range(1, 256)])
print(f"(1) live making gauge, {len(mk)} UIDs reported: x3 now {mk.get(64, 0):.0f}; projected steady {SM:.0f}")
print(f"    UIDs BELOW {SM:.0f}: {int((vals < SM).sum())} of 255 | percentiles p10 {np.percentile(vals, 10):.0f} p25 {np.percentile(vals, 25):.0f} median {np.median(vals):.0f} p75 {np.percentile(vals, 75):.0f}")
for thr in (250, 300, 335, 400, 500):
    print(f"      below {thr}: {int((vals < thr).sum())}")
er = np.array([E[u] / line for u in non])
print(f"(2) chain pay ÷ prune line, {len(non)} unprotected UIDs (+ {int(prot.sum())} protected newcomers): x3 steady est {SR:.2f}×")
for thr in (1.1, 1.2, 1.25, 1.3, 1.5, 2.0):
    print(f"      unprotected UIDs below {thr:.2f}×: {int((er < thr).sum())}  (of which fleet {sum(1 for u in non if E[u] / line < thr and u in fleet)})")
print(f"    field median {np.median(er):.2f}× | p25 {np.percentile(er, 25):.2f}× | p10 {np.percentile(er, 10):.2f}×")
