"""SN50 calibration by horizon (decisions.md §1216): for each scored Crypto-24h prompt, where the realized price change falls inside our
1,000-path ensemble (PIT) at the scoring horizons — 5 min (all 288 steps), 30 min, 3 h, 24 h — and the ensemble's spread vs the realized
|change| (width ratio). Calibrated: 50% inside the central 50%, 10% outside the 5-95% band, width ratio ≈ 1.
    python -m futuresres.synth.s50_calib BTC 5 todg_12_144_c_ou20@1.0"""
import datetime as dt, json, sys
import numpy as np
from futuresres.synth import s50_backtest as B
asset, days, model = sys.argv[1], int(sys.argv[2]), sys.argv[3]
P = B.prompts(asset, days); starts = sorted(P)
t_lo = int(dt.datetime.fromisoformat(starts[0].replace("Z", "+00:00")).timestamp() * 1000) - 32 * 86400000
t_hi = int(dt.datetime.fromisoformat(starts[-1].replace("Z", "+00:00")).timestamp() * 1000)
M = B.minutes(asset, t_lo, t_hi); keys = np.array(sorted(M)); vals = np.array([M[k] for k in keys]); rng = np.random.default_rng(1216)
H = {"5min": 1, "30min": 6, "3hour": 36, "24hour": 288}
pit = {h: [] for h in H}; width = {h: [] for h in H}
for st in starts:
    real = B.realized(asset, st)
    if not real or len(real) < 289: continue
    t0 = int(dt.datetime.fromisoformat(st.replace("Z", "+00:00")).timestamp() * 1000)
    i = np.searchsorted(keys, t0 - 60000, side="right")
    if i < 31 * 1440: continue
    hist = vals[i - 31 * 1440:i]; slot0 = (t0 // 300000) % 288; day0 = dt.datetime.fromtimestamp(t0 / 1000, dt.timezone.utc).weekday()
    paths = B.ensemble(hist, float(hist[-1]), model.split("@")[0], rng, slot0=slot0, k=float(model.split("@")[1]) if "@" in model else 1.0, stride=5, day0=day0)
    lp = np.log(paths); lr = np.log(np.array(real, float))
    for h, s in H.items():
        for a in range(0, 288 - s + 1, s):                  # non-overlapping intervals of that length
            ens = lp[:, a + s] - lp[:, a]; x = lr[a + s] - lr[a]
            pit[h].append(float((ens < x).mean())); width[h].append(float(np.std(ens)) / max(abs(x), 1e-9))
out = {}
for h in H:
    p = np.array(pit[h]); out[h] = {"n": len(p), "central50": round(float(((p > 0.25) & (p < 0.75)).mean()), 3),
                                    "tails10": round(float(((p < 0.05) | (p > 0.95)).mean()), 3), "below_mid": round(float((p < 0.5).mean()), 3)}
print(json.dumps({"asset": asset, "days": days, "model": model, **out}))
