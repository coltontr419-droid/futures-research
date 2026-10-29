# A128 (decisions.md 1102): MNQ (NQ-spliced) RTH 09:30-16:00 ET minute paths for 2010-06 -> 2015-11-19 (sessions the A08 cache drops: its loader needs a
# complete 18:00-16:55 session), drift removed, scaled to today's MNQ notional like A08; then the Fast Track 50K and 100K plans on this untouched era.
# Run: python scripts/a128_mnq_2010_15.py
import numpy as np, polars as pl
from pathlib import Path
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a123_fast_track_policy import simulate
from futuresres.reporting.a124_fast_track_sizes import SIZES
ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "data" / "continuous" / "NQ_MNQ_spliced.parquet"
et = pl.col("ts_event").dt.convert_time_zone("America/New_York")
df = (pl.scan_parquet(S).filter(pl.col("session") < pl.date(2015, 11, 20)).select("ts_event", "session", "open", "high", "low", "close")
      .with_columns((et.dt.hour().cast(pl.Int32) * 60 + et.dt.minute().cast(pl.Int32) - 570).alias("m"))
      .filter((pl.col("m") >= 0) & (pl.col("m") < 390)).sort("ts_event").collect())
today = float(pl.scan_parquet(S).select(pl.col("close").sort_by("ts_event").last()).collect().item()) * 2.0
sess = df["session"].to_numpy(); m = df["m"].to_numpy(); o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
keys, idx = np.unique(sess, return_index=True); b = np.r_[idx, len(sess)]
H, L, C, D = [], [], [], []
for s in range(len(keys)):
    mm = m[b[s]:b[s + 1]]
    if mm[0] != 0 or mm[-1] < 385 or len(mm) < 300:
        continue
    p0 = o[b[s]]; hh = np.full(390, np.nan); ll = hh.copy(); cc = hh.copy()
    hh[mm] = h[b[s]:b[s + 1]]; ll[mm] = l[b[s]:b[s + 1]]; cc[mm] = c[b[s]:b[s + 1]]
    cc = np.array(pl.Series(cc).fill_null(strategy="forward").fill_nan(None).fill_null(strategy="forward").fill_null(p0).to_numpy(), float)
    hh = np.where(np.isnan(hh), cc, hh); ll = np.where(np.isnan(ll), cc, ll)
    H.append(hh / p0 - 1); L.append(ll / p0 - 1); C.append(cc / p0 - 1); D.append(keys[s])
H, L, C = (np.array(x) for x in (H, L, C))
mu = C[:, -1].mean(); ramp = np.arange(1, 391) / 390
h, l, c = ((x - mu * ramp) * today for x in (H, L, C))
print(f"sessions {len(D)} ({D[0]} -> {D[-1]}), mean RTH drift removed {mu*1e4:.1f} bps, today's notional ${today:,.0f}")
for name, W, Lx in (("50K", 650.0, 2000.0), ("100K", 800.0, 4000.0)):
    T = dict(TERMS, **SIZES[name])
    for side in (1, -1):
        hh, ll, cc = (h, l, c) if side > 0 else (-l, -h, -c)
        v, pp = simulate(hh, ll, cc, Lx and W, Lx, 0, None, T)
        wins = [simulate(hh[s:s + 84], ll[s:s + 84], cc[s:s + 84], W, Lx, 0, None, T)[0] for s in range(0, len(cc) - 84, 3)]
        w = np.array(wins)
        print(f"{name:5} {'long' if side > 0 else 'short':5} continuous {v:+7,.0f} per 84 ({pp:.1f} accts/payout) | fresh 84-windows mean {w.mean():+7,.0f} P>0 {np.mean(w > 0):.0%} p10 {np.percentile(w, 10):+7,.0f} worst {w.min():+7,.0f}", flush=True)
