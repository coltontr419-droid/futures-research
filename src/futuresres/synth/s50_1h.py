"""SN50 Crypto-1h backtest (1-minute steps, 1-hour horizon; price CRPS over 1/2/5/15/30/60-min changes and the 5..60-min gaps, plus the volatility
term; softmax beta 0.3). Same method as s50_backtest (decisions.md §1164, §1166): every scored prompt's realized path and the field's scores from the
Synth API; our 1,000-path ensemble from Binance 1-minute closes known before t0.

    python -m futuresres.synth.s50_1h BTC 3 [models]
"""

from __future__ import annotations

import datetime as dt
import json
import sys

import numpy as np

from futuresres.synth.competition_config_upstream import CRYPTO_1H
from futuresres.synth.fast_crps import crps_sum, vol_crps
from futuresres.synth.s50_backtest import API, CACHE, get, minutes


def prompts(asset: str, days: int):
    f = CACHE / f"scores1h_{asset}_{days}.json"
    if f.exists():
        return json.loads(f.read_text())
    end = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0); out = {}
    for h in range(days * 24):
        a = end - dt.timedelta(hours=h + 1); b = end - dt.timedelta(hours=h)
        rows = get(f"{API}/validation/scores/historical", {"from": a.strftime("%Y-%m-%dT%H:%M:%SZ"), "to": b.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                            "asset": asset, "time_increment": 60, "time_length": 3600}, required=False) or []
        for r in rows:
            st = (dt.datetime.fromisoformat(r["scored_time"].replace("Z", "+00:00")) - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            out.setdefault(st, {})[str(r["miner_uid"])] = r["crps"]
    CACHE.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(out))
    return out


def realized(asset: str, start: str):
    f = CACHE / f"real1h_{asset}_{start.replace(':', '')}.json"
    if f.exists():
        return json.loads(f.read_text())
    r = get(f"{API}/validation/realized-path", {"start_time": start, "asset": asset, "time_increment": 60, "time_length": 3600}, required=False)
    p = (r or {}).get("real_prices")
    if p:
        f.write_text(json.dumps(p))
    return p


def ensemble(closes: np.ndarray, s0: float, slot0: int, model: str, rng, k: float = 1.0, n=1000, steps=60) -> np.ndarray:
    """1-minute paths. 'tod1_<hl>_<dec>': minute-of-day vol profile (30 days, smoothed) x EWMA level (half-life hl minutes) reverting to the
    7-day level over dec minutes; shocks bootstrapped from residuals standardised by profile and local level."""
    r = np.diff(np.log(closes)); m = len(r); slots = (slot0 - m + np.arange(m)) % 1440
    prof = np.array([np.sqrt(np.mean(r[slots == j] ** 2)) for j in range(1440)])
    prof = np.convolve(np.r_[prof[-7:], prof, prof[:7]], np.ones(15) / 15, "valid")
    z = r / prof[slots]
    hl, dec = (float(x) for x in model.split("_")[1:3])
    a = 1 - 0.5 ** (1 / hl); v = np.empty(m); acc = np.mean(z[:1440] ** 2)
    for t in range(m):
        v[t] = acc; acc = (1 - a) * acc + a * z[t] ** 2
    level = np.sqrt(acc); long = np.sqrt(np.mean(z[-10080:] ** 2))
    lev = long + (level - long) * np.exp(-np.arange(steps) / dec)
    zc = z / np.sqrt(v); pool = zc[-20160:] / np.sqrt(np.mean(zc[-20160:] ** 2))
    fut = prof[(slot0 + np.arange(steps)) % 1440] * lev * k
    inc = rng.choice(pool, (n, steps)) * fut[None, :]
    return s0 * np.exp(np.concatenate([np.zeros((n, 1)), np.cumsum(inc, axis=1)], axis=1))


def score(paths, real):
    return crps_sum(paths, real, 60, CRYPTO_1H.scoring_intervals) + vol_crps(paths, real, 60, CRYPTO_1H.vol_scoring_blocks)


def main(asset: str, days: int, models=("tod1_30_60", "tod1_60_120", "tod1_15_30", "tod1_30_60@0.95")) -> dict:
    P = prompts(asset, days); starts = sorted(P)
    t_lo = int(dt.datetime.fromisoformat(starts[0].replace("Z", "+00:00")).timestamp() * 1000) - 32 * 86400000
    t_hi = int(dt.datetime.fromisoformat(starts[-1].replace("Z", "+00:00")).timestamp() * 1000)
    M = minutes(asset, t_lo, t_hi); keys = np.array(sorted(M)); vals = np.array([M[k] for k in keys])
    rng = np.random.default_rng(1166); rows = []
    for st in starts:
        real = realized(asset, st)
        if not real or len(real) < 61 or len(P[st]) < 100:
            continue
        t0 = int(dt.datetime.fromisoformat(st.replace("Z", "+00:00")).timestamp() * 1000)
        i = np.searchsorted(keys, t0 - 60000, side="right")
        if i < 31 * 1440:
            continue
        hist = vals[i - 31 * 1440:i]; s0 = float(hist[-1]); slot0 = (t0 // 60000) % 1440
        ours = {m: score(ensemble(hist, s0, slot0, m.split("@")[0], rng, float(m.split("@")[1]) if "@" in m else 1.0), np.array(real, float)) for m in models}
        rows.append({"start": st, "field": P[st], **ours})
    from futuresres.synth.s50_backtest import summarise
    out = summarise(rows, models, beta=0.3)
    (CACHE / f"bt1h_{asset}_{days}.json").write_text(json.dumps({"summary": out, "n_prompts": len(rows)}, indent=1))
    return out


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], int(sys.argv[2]), *([tuple(sys.argv[3].split(","))] if len(sys.argv) > 3 else [])), indent=1))
