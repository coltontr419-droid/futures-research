"""SN50 Com/Equ session diagnosis (decisions.md §1217): for a Hyperliquid equity/commodity perp, (1) realized 5-minute volatility by session —
US cash hours (09:30-16:00 ET, Mon-Fri), weekday closed hours, weekends — from the validator's Hyperliquid feed (hl5 cache); (2) our
model's PIT calibration of realized 5-min / 30-min / 3-h changes by the session the interval starts in; (3) the open: |change| in the first
30 min of cash hours vs the same model's spread there.
    python -m futuresres.synth.s50_session SP500 5 todg_12_36_c_yp@1.0"""
import datetime as dt, json, sys
from zoneinfo import ZoneInfo
import numpy as np
from futuresres.synth import s50_backtest as B
ET = ZoneInfo("America/New_York")
asset, days, model = sys.argv[1], int(sys.argv[2]), sys.argv[3]
def session(ms):
    t = dt.datetime.fromtimestamp(ms / 1000, ET)
    if t.weekday() >= 5: return "weekend"
    m = t.hour * 60 + t.minute
    return "cash" if 570 <= m < 960 else "closed"
M = B.hl5(asset); keys = np.array(sorted(M)); vals = np.array([M[k] for k in keys])
r = np.diff(np.log(vals)); lab = [session(int(k)) for k in keys[1:]]
print("realized 5-min vol (bp) by session, last ~17 days:", {s: round(float(np.sqrt(np.mean(np.array([x for x, l in zip(r, lab) if l == s]) ** 2)) * 1e4), 2)
      for s in ("cash", "closed", "weekend")})
P = B.prompts(asset, days); H = B.hl1h(asset); Y = B.yahoo5(asset) if asset in B.YAHOO else None; rng = np.random.default_rng(1217)
hz = {"5min": 1, "30min": 6, "3hour": 36}; pit = {}
for st in sorted(P):
    real = B.realized(asset, st)
    if not real or len(real) < 289: continue
    t0 = int(dt.datetime.fromisoformat(st.replace("Z", "+00:00")).timestamp() * 1000)
    i = np.searchsorted(keys, t0 - 300000, side="right")
    if i < 16 * 288: continue
    hist = vals[i - 16 * 288:i] if model.startswith("ses") else vals[i - 6 * 288:i]; slot0 = (t0 // 300000) % 288; day0 = dt.datetime.fromtimestamp(t0 / 1000, dt.timezone.utc).weekday()
    hp = B.hour_profile(H, t0) if H else None
    if hp is not None and Y is not None: hp = (hp[0], hp[1], B.yahoo_profile(Y, t0))
    paths = B.ses_ensemble(hist, float(hist[-1]), model.split("@")[0], rng, t0, k=float(model.split("@")[1]) if "@" in model else 1.0) if model.startswith("ses") else B.ensemble(hist, float(hist[-1]), model.split("@")[0], rng, slot0=slot0, k=float(model.split("@")[1]) if "@" in model else 1.0, stride=1, day0=day0, hprof=hp)
    lp = np.log(paths); lr = np.log(np.array(real, float))
    for h, s in hz.items():
        for a in range(0, 288 - s + 1, s):
            ss = session(t0 + a * 300000); ens = lp[:, a + s] - lp[:, a]; x = lr[a + s] - lr[a]
            pit.setdefault((h, ss), []).append((float((ens < x).mean()), float(np.std(ens)), abs(float(x))))
print(f"model {model}: PIT by horizon and session (calibrated: central50 0.50, tails10 0.10; width = model sd / realized |change| median)")
for (h, ss), v in sorted(pit.items()):
    p = np.array([x[0] for x in v]); sd = np.array([x[1] for x in v]); rx = np.array([x[2] for x in v])
    print(f"  {h:6} {ss:8} n {len(p):5} | central50 {((p > .25) & (p < .75)).mean():.2f} tails10 {((p < .05) | (p > .95)).mean():.2f} | model sd {np.median(sd)*1e4:6.2f} bp vs realized |chg| median {np.median(rx)*1e4:6.2f} bp")
