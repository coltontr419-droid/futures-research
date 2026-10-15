"""A50 - strategy library batch 1: MNQ intraday (decisions.md 584). Discovery 2021-24, validation 2025-26, account replay.

    python -m futuresres.reporting.a50_stratlib --scan          (discovery: per-trade net on 2021-24, all variants)
    python -m futuresres.reporting.a50_stratlib --validate X    (one variant, sealed 2025-26 + account replay)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a27_standalone as a27
import futuresres.reporting.d8_intraday as d8

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a50_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
COST_BPS = 0.56                     # MNQ round trip, bps (§16 / d16)
VARIANTS = ("ORB15", "ORB30", "VB0.3", "VB0.5", "FH", "ON")
_G: dict = {}


def grid(session: str):
    if session not in _G:
        D, C, _, K = d8.load("MNQ", session)
        _G[session] = (D, C, K)
    return _G[session]


def trades(var: str) -> list:
    """[(date, direction +1/-1, session, entry offset)] - one per session at most; same-contract windows only."""
    out = []
    if var == "ON":
        D, C, K = grid("night")
        for i, d in enumerate(D):
            c = C[i]
            if np.isfinite(c[0]) and np.isfinite(c[-1]) and K[i, 0] == K[i, -1]:
                out.append((d, 1, "night", 0))
        return out
    D, C, K = grid("day"); prev_rng = None
    for i, d in enumerate(D):
        c = C[i]; ok = np.isfinite(c).all() and K[i, 0] == K[i, -1]
        if not ok:
            prev_rng = None; continue
        if var.startswith("ORB"):
            m = int(var[3:]); hi, lo = c[:m].max(), c[:m].min()
            for j in range(m, len(c) - 1):
                if c[j] > hi:
                    out.append((d, 1, "day", j)); break
                if c[j] < lo:
                    out.append((d, -1, "day", j)); break
        elif var.startswith("VB") and prev_rng:
            k = float(var[2:]); up, dn = c[0] + k * prev_rng, c[0] - k * prev_rng
            for j in range(1, len(c) - 1):
                if c[j] >= up:
                    out.append((d, 1, "day", j)); break
                if c[j] <= dn:
                    out.append((d, -1, "day", j)); break
        elif var == "FH":
            s = np.sign(c[60] - c[0])
            if s:
                out.append((d, int(s), "day", 60))
        prev_rng = float(c.max() - c.min())
    return out


def net_bps(t) -> float:
    d, s, sess, j = t; D, C, K = grid(sess); i = list(D).index(d) if False else _idx(sess)[d]
    c = C[i]
    return s * (c[-1] / c[j] - 1) * 1e4 - COST_BPS


_I: dict = {}


def _idx(sess):
    if sess not in _I:
        _I[sess] = {d: i for i, d in enumerate(grid(sess)[0])}
    return _I[sess]


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = {}
    for v in VARIANTS:
        T = trades(v); row = {}
        for per, (lo, hi) in (("2010-20", CONTEXT), ("2021-24", DISC)):
            x = np.array([net_bps(t) for t in T if lo <= t[0] <= hi])
            row[per] = {"n": int(len(x)), "net": float(x.mean()), "t": _t(x), "hit": float((x > 0).mean())}
        row["carried"] = bool(row["2021-24"]["net"] > 0 and row["2021-24"]["t"] > 1.96)
        res[v] = row
        print(f"{v:6}: 2021-24 n {row['2021-24']['n']:4} net {row['2021-24']['net']:+6.2f} t {row['2021-24']['t']:+5.2f} | 2010-20 n {row['2010-20']['n']:4} "
              f"net {row['2010-20']['net']:+6.2f} t {row['2010-20']['t']:+5.2f}{'  CARRIED' if row['carried'] else ''}", flush=True)
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true"); a = ap.parse_args()
    if a.scan:
        scan()


def validate(var: str, hid: str, order_z: int) -> dict:
    """Sealed 2025-26, once: §426 rule; placebo = random directions on the same entries (1000)."""
    from futuresres.signals.z_strict import T_CRIT
    from futuresres.stats.trials import Trial, TrialLog
    T = [t for t in trades(var) if VAL[0] <= t[0] <= VAL[1]]
    x = np.array([net_bps(t) for t in T]); gross = x + COST_BPS
    disc = json.loads(OUT.read_text())[var]["2021-24"]["net"]
    rng = np.random.default_rng(5840 + int(hid[1:])); mu = disc / 2; noise = x - x.mean()
    est = np.array([(rng.choice(noise, len(x)) + mu).mean() for _ in range(2000)])
    inj = {"hypothesis": hid, "n_events": int(len(x)), "sought_bps": mu, "mean_estimate": float(est.mean()),
           "recovered": bool(abs(est.mean() - mu) <= 3 * est.std(ddof=1) / math.sqrt(2000) + 0.5)}
    (ROOT / "reports" / f"{hid.lower()}_injection.json").write_text(json.dumps(inj, indent=1) + "\n")
    t = _t(x); rng = np.random.default_rng(58400 + int(hid[1:]))
    draws = np.array([(rng.choice([-1, 1], len(x)) * np.abs(gross) * np.sign(gross) - COST_BPS).mean() for _ in range(1000)])
    pct = float((draws < x.mean()).mean() * 100)
    yrs = np.array([d.year for d, *_ in T]); by = {int(y): float(x[yrs == y].mean()) for y in sorted(set(yrs))}
    ca, cb, cc = t > T_CRIT, pct >= 95.0, all(by.get(y, -1) > 0 for y in (2025, 2026))
    tier = "CONFIRM" if (ca and cb and cc) else ("WATCHLIST" if x.mean() > 0 else "REJECT")
    out = {"hypothesis": hid, "cell": f"MNQ {var} intraday strategy", "trades": int(len(x)), "net_bps": float(x.mean()), "t_net": t,
           "placebo_pct": pct, "by_year": by, "conditions": {"a": bool(ca), "b": bool(cb), "c": bool(cc)}, "decision": tier,
           "z_d_market_test_number": order_z, "injection": inj}
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol="MNQ", date_range=(str(T[0][0]), str(T[-1][0])), status="completed",
                           sharpe=float(x.mean() / x.std(ddof=1)), params={"statistic": f"MNQ {var}; sealed 2025-2026; decisions.md 426 rule",
                                                                          "net_bps": float(x.mean()), "t_net": t, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (A50 strategy library, decisions.md 584-585); validated once on sealed data."))
    out["trial_id"] = rec["trial_id"]
    (ROOT / "reports" / f"{hid.lower()}_trial.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"{hid} MNQ {var}: {tier} | n {len(x)} net {x.mean():+.2f} t {t:+.2f} placebo {pct:.0f} | " + ", ".join(f"{y} {v:+.1f}" for y, v in by.items()) + f" | {rec['trial_id']}", flush=True)
    return out


def paths(var: str, era: str):
    """Per RTH session (the replay's calendar): one-contract $ paths from the strategy's entry, padded flat; no-trade sessions skipped."""
    D, C, K = grid("day"); T = {t[0]: t for t in trades(var)}
    lo, hi = (dt.date(2010, 1, 1), dt.date(2020, 12, 31)) if era == "pre" else (dt.date(2021, 1, 1), dt.date(2026, 8, 31))
    usd = float(C[np.isfinite(C[:, -1]), -1][-1]) * 2.0; L = C.shape[1]
    H, dates, skip, sgn = [], [], [], []
    for i, d in enumerate(D):
        if not (lo <= d <= hi):
            continue
        c = C[i]
        if d in T and np.isfinite(c).all():
            _, s, _, j = T[d]; p = np.full(L, np.nan); p[: L - j] = (c[j:] / c[j] - 1); p[L - j:] = p[L - j - 1]
            H.append(p * usd); skip.append(False); sgn.append(s)
        else:
            H.append(np.zeros(L)); skip.append(True); sgn.append(1)
        dates.append(d)
    P = np.array(H, np.float32)
    return P, np.array(skip), np.array(sgn), dates


def account(var: str, n_random: int = 100) -> dict:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; n, rt = a23.MARKETS["MNQ"]; out = {}
    for era in ("pre", "post"):
        P, skip, sgn, dates = paths(var, era)
        st = np.array(dates[: len(dates) - 84]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st])
        short = sgn < 0; h, l, c = a27.flip(P, P, P, short)
        r = a23.replay(s, (h, l, c), n, rt, skip=skip)
        trade_idx = np.where(~skip)[0]; rng = np.random.default_rng(585); rnd = []
        for _ in range(n_random):
            sh = short.copy(); sh[trade_idx] = rng.random(len(trade_idx)) < 0.5
            rnd.append(a23.replay(s, a27.flip(P, P, P, sh), n, rt, skip=skip)["net"])
        rnd = np.array(rnd)
        row = {"trade_days": float((~skip).mean()), "mean": float(r["net"].mean()), "p_payout": float((r["first"] > 0).mean()),
               "random": float(rnd.mean()), "beats": float((rnd.mean(1) < r["net"].mean()).mean() * 100)}
        if m25.any():
            row.update({"mean_2025": float(r["net"][m25].mean()), "p_payout_2025": float((r["first"][m25] > 0).mean()),
                        "random_2025": float(rnd[:, m25].mean()), "beats_2025": float((rnd[:, m25].mean(1) < r["net"][m25].mean()).mean() * 100)})
        out[era] = row
        print(f"MNQ {var} account {era}: trades {row['trade_days']:.0%} of days; mean {row['mean']:+7,.0f} P(payout) {row['p_payout']:.0%} | random dir "
              f"{row['random']:+7,.0f} beats {row['beats']:.0f}%" + (f" | 2025 starts {row['mean_2025']:+7,.0f} ({row['p_payout_2025']:.0%}) random "
              f"{row['random_2025']:+7,.0f} beats {row['beats_2025']:.0f}%" if m25.any() else ""), flush=True)
    return out
