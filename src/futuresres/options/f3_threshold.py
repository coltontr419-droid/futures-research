"""F-family 3 (decisions.md 1085): options-implied P(close > K) vs a realized-vol lognormal on synthetic threshold questions. No trial.

    python -m futuresres.options.f3_threshold fetch      # DoltHub call chains (every 5th snapshot) + Yahoo daily closes
    python -m futuresres.options.f3_threshold            # score
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import NormalDist

import numpy as np

from futuresres.options.x1_straddle import sql
from futuresres.options.x3_cheapvol import snaps

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "options" / "f3"
SYMS = ["SPY", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD", "NFLX", "JPM", "XOM", "LLY", "COST", "WMT",
        "ORCL", "PLTR", "MU", "INTC", "BA"]
SEAL, LAST = "2024-01-01", "2026-10-23"
N = NormalDist()


def dates() -> list[str]:
    return [d for d in snaps() if d >= "2020-01-01"][::5]


def fetch() -> None:
    OUT.mkdir(parents=True, exist_ok=True); f = OUT / "chains.jsonl"
    done = {(r["date"], r["group"]) for r in map(json.loads, open(f))} if f.exists() else set()
    groups = [SYMS[i:i + 7] for i in range(0, len(SYMS), 7)]
    jobs = [(d, g) for d in dates() for g in range(len(groups)) if (d, g) not in done]
    print(len(jobs), "chain queries", flush=True)

    def one(job):
        d, g = job; hi = (dt.date.fromisoformat(d) + dt.timedelta(days=60)).isoformat()
        syms = ",".join(f"'{s}'" for s in groups[g])
        rows = sql(f"SELECT act_symbol, expiration, strike, vol, delta FROM option_chain WHERE date='{d}' AND call_put='Call' "
                   f"AND act_symbol IN ({syms}) AND expiration <= '{hi}' AND delta BETWEEN 0.03 AND 0.97")
        return d, g, rows

    with ThreadPoolExecutor(4) as ex, open(f, "a") as fo:
        for k, (d, g, rows) in enumerate(ex.map(one, jobs)):
            if rows is None:
                print("  failed", d, g, flush=True); continue
            fo.write(json.dumps({"date": d, "group": g, "rows": [[r["act_symbol"], r["expiration"], float(r["strike"]), float(r["vol"] or 0),
                                                                     float(r["delta"] or 0)] for r in rows]}) + "\n"); fo.flush()
            if k % 50 == 0:
                print(" ", k, d, len(rows), flush=True)
    for s in SYMS:
        p = OUT / f"y_{s}.json"
        if not p.exists():
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?interval=1d&period1=1546300800&period2={int(time.time())}"
            p.write_bytes(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read())
            time.sleep(1)


def closes(s: str) -> dict:
    r = json.loads((OUT / f"y_{s}.json").read_text())["chart"]["result"][0]
    q = r["indicators"]["quote"][0]["close"]          # raw close: options strikes are in raw (split-unadjusted) prices
    return {dt.datetime.fromtimestamp(t, dt.timezone(dt.timedelta(hours=-5))).date().isoformat(): c for t, c in zip(r["timestamp"], q) if c}


def questions() -> list[tuple]:
    """(sym, date, expiry, K, p_module_parts(delta, iv, T), p_baseline, outcome)."""
    C = {s: closes(s) for s in SYMS}; out = []
    for rec in map(json.loads, open(OUT / "chains.jsonl")):
        d = rec["date"]
        for s, ex, K, iv, delta in rec["rows"]:
            T = (dt.date.fromisoformat(ex) - dt.date.fromisoformat(d)).days
            if not (5 <= T <= 60) or ex > LAST or iv <= 0 or not (0.03 <= delta <= 0.97):
                continue
            c = C[s]; days = sorted(x for x in c if x <= d)
            if not days or days[-1] < (dt.date.fromisoformat(d) - dt.timedelta(days=4)).isoformat() or len(days) < 21:
                continue
            S0 = c[days[-1]]; r = np.diff(np.log([c[x] for x in days[-21:]])); rv = float(r.std(ddof=1) * math.sqrt(252))
            e = sorted(x for x in c if x <= ex)
            if not e or e[-1] < (dt.date.fromisoformat(ex) - dt.timedelta(days=4)).isoformat():
                continue
            if abs(math.log(K / S0)) > 1.0:                   # split mismatch guard
                continue
            out.append((s, d, ex, K, delta, iv, T / 365.0, S0, rv, 1.0 if c[e[-1]] > K else 0.0))
    return out


def p_module(delta, iv, T, cfac=1.0):
    d1 = N.inv_cdf(min(max(delta, 1e-6), 1 - 1e-6))
    if cfac != 1.0:                                       # rescale: recover ln(F/K) from d1 at the market iv, re-evaluate at c * iv
        x = d1 * iv * math.sqrt(T) - 0.5 * iv * iv * T
        s = cfac * iv
        return N.cdf((x - 0.5 * s * s * T) / (s * math.sqrt(T)))
    return N.cdf(d1 - iv * math.sqrt(T))


def p_base(S0, K, rv, T):
    s = max(rv, 1e-4)
    return N.cdf((math.log(S0 / K) - 0.5 * s * s * T) / (s * math.sqrt(T)))


def score() -> int:
    Q = questions(); print(len(Q), "questions", flush=True)
    tr = [q for q in Q if q[1] < SEAL]; se = [q for q in Q if q[1] >= SEAL]
    brier = lambda P, Y: float(np.mean((np.array(P) - np.array(Y)) ** 2))
    grid = [round(0.70 + 0.025 * i, 3) for i in range(17)]
    fit = {c: brier([p_module(q[4], q[5], q[6], c) for q in tr], [q[9] for q in tr]) for c in grid}
    cbest = min(fit, key=fit.get); print("train Brier by c:", {c: round(v, 5) for c, v in fit.items()}, "-> c", cbest)
    res = {"n_train": len(tr), "n_sealed": len(se), "c": cbest}
    Y = np.array([q[9] for q in se]); clus = np.array([hash((q[0], q[1])) for q in se])
    PB = np.array([p_base(q[7], q[3], q[8], q[6]) for q in se])
    for name, cf in (("M", 1.0), ("M_c", cbest)):
        PM = np.array([p_module(q[4], q[5], q[6], cf) for q in se])
        for metric, f in (("brier", lambda p: (p - Y) ** 2),
                          ("log", lambda p: -(Y * np.log(np.clip(p, 1e-4, 1)) + (1 - Y) * np.log(np.clip(1 - p, 1e-4, 1))))):
            dlt = f(PM) - f(PB)                            # negative = module better
            u = np.unique(clus, return_inverse=True)[1]; sums = np.bincount(u, dlt); cnt = np.bincount(u)
            m = sums.sum() / cnt.sum(); g = sums - m * cnt; se_ = math.sqrt((g ** 2).sum()) / cnt.sum()
            res[f"{name}_{metric}"] = {"module": float(f(PM).mean()), "baseline": float(f(PB).mean()), "diff": float(m), "t": float(m / se_)}
            print(f"{name:3} {metric:5}: module {f(PM).mean():.5f} baseline {f(PB).mean():.5f} diff {m:+.5f} (clustered t {m / se_:+.2f}, {len(set(u))} clusters)")
        cal = []
        for lo, hi in ((0, .05), (.05, .15), (.15, .3), (.3, .5), (.5, .7), (.7, .85), (.85, .95), (.95, 1.01)):
            for lab, P in (("module", PM), ("baseline", PB)):
                k = (P >= lo) & (P < hi)
                if k.sum():
                    cal.append([name, lab, lo, hi, int(k.sum()), float(P[k].mean()), float(Y[k].mean()), float(math.sqrt(Y[k].mean() * (1 - Y[k].mean()) / k.sum()))])
        res[f"{name}_calibration"] = cal
        for r in cal:
            if r[1] == "module" or name == "M":
                print(f"   {r[0]:3} {r[1]:8} p in [{r[2]:.2f},{r[3]:.2f}): n {r[4]:6}  mean p {r[5]:.3f}  observed {r[6]:.3f} (±{r[7]:.3f})")
    (ROOT / "reports" / "f3_threshold.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["fetch"]:
        fetch(); raise SystemExit(0)
    raise SystemExit(score())
