"""Re-derive the crypto-24h share with the validator's per-asset coefficients and a sanity check: does the same method reproduce the REAL top UID's share (API: ≈ 2.6% of the competition)?"""
import json, glob, os, numpy as np, collections
COEF = {"BTC": 1.0, "ETH": 0.7064366394033871, "SOL": 0.6310037175639559, "XRP": 0.5658394110809131, "HYPE": 0.4784547133706857}
MODEL = "todg_12_144_c_ou20@1.0"; BETA = 0.15
days = sorted(d for d in glob.glob("/opt/synth/data/synth/forward/2026-11-*") if not d.endswith("backfill"))[-10:]
for cap_pct in (90, 95):
  for use_coef in (False, True):
    per_uid = collections.defaultdict(list); us = []; n = 0
    for d in days:
        for a in COEF:
            fs, fr = f"{d}/scores24_{a}.json", f"{d}/rows24_{a}.json"
            if not (os.path.exists(fs) and os.path.exists(fr)): continue
            S = json.load(open(fs)); R = {r["start"]: r for r in json.load(open(fr))}
            for start, field in S.items():
                r = R.get(start)
                if not r or MODEL not in r: continue
                uids = list(field); v = np.array([field[u] for u in uids] + [r[MODEL]], float)
                ok = v > 0; cap = np.percentile(v[ok], cap_pct); v = np.where(ok, np.minimum(v, cap), cap); v = v - v.min()
                w = COEF[a] if use_coef else 1.0
                for u, x in zip(uids, v[:-1]): per_uid[u].append(x * w)
                us.append(v[-1] * w); n += 1
    L = {u: np.mean(x) for u, x in per_uid.items() if len(x) >= 0.8 * n}
    Lf = np.array(list(L.values())); Lus = np.mean(us)
    wf = np.exp(-BETA * Lf); wu = np.exp(-BETA * Lus)
    field_only = np.sort(wf / wf.sum())[::-1]
    ordr = sorted(L, key=L.get)[:5]; print("   lowest-L uids", [(u, round(L[u], 1), len(per_uid[u])) for u in ordr])
    print(f"cap p{cap_pct} coef {use_coef}: prompts {n}, field UIDs {len(Lf)} | FIELD ONLY top shares {[round(x*100, 2) for x in field_only[:4]]}% | WITH US: our share {wu/(wu + wf.sum())*100:.1f}%, "
          f"L_us {Lus:.1f} vs field best {Lf.min():.1f} / median {np.median(Lf):.1f}")
