"""A78 - the staking game in a static-floor, on-demand-payout crypto prop (Breakout Classic 1-step as modelled; decisions.md 684).

    python -m futuresres.reporting.a78_crypto_prop
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
U = 0.0025                                   # one unit = 0.25% of the account
TARGET, FLOOR, DAILY = 40, -24, 12          # +10%, -6%, 3% (units)
FEE_PCT, SPLIT = 0.01, 0.80
COST_SIDE = 0.0005 + 0.0002                  # taker + slippage, of notional, a side
STOP_DIST = 0.03                             # the stop's distance in BTC price (notional = stop / 3%)
L_SET = (2, 4, 6, 8, 10, 12)
W_SET = tuple(range(2, 42, 2))


def cost_units(L: int) -> float:
    return (L * U / STOP_DIST) * 2 * COST_SIDE / U


def solve(H: int):
    """(eval policy, funded policy, P(pass within H), funded value within H in units of the account)."""
    bs_e = np.arange(FLOOR + 1, TARGET)                          # alive evaluation balances
    Ve = np.zeros(len(bs_e)); pe = np.zeros((len(bs_e), 2), int)
    bs_f = np.arange(FLOOR + 1, 1)                               # funded balances after withdrawals (<= 0)
    Vf = np.zeros(len(bs_f)); pf = np.zeros((len(bs_f), 2), int)
    for _ in range(H):
        nVe = np.zeros_like(Ve); nVf = np.zeros_like(Vf)
        npe = np.zeros_like(pe); npf = np.zeros_like(pf)
        for i, b in enumerate(bs_e):
            best = -1.0; act = (0, 0)                            # always trade (A01; waiting forever pays nothing)
            for L in L_SET:
                if b - L <= FLOOR and L < b - FLOOR:
                    continue
                Le = min(L, b - FLOOR); c = cost_units(Le)
                for W in W_SET:
                    p = max(Le - c, 0) / (W + Le)
                    vw = 1.0 if b + W >= TARGET else Ve[b + W - (FLOOR + 1)]
                    vl = 0.0 if b - Le <= FLOOR else Ve[b - Le - (FLOOR + 1)]
                    v = p * vw + (1 - p) * vl
                    if v > best + 1e-12:
                        best, act = v, (W, Le)
            nVe[i] = best; npe[i] = act
        for i, b in enumerate(bs_f):
            best = -1.0; act = (0, 0)
            for L in L_SET:
                Le = min(L, b - FLOOR); c = cost_units(Le)
                for W in W_SET:
                    p = max(Le - c, 0) / (W + Le)
                    up = b + W; paid = SPLIT * max(up, 0) * U; vw = paid + Vf[min(up, 0) - (FLOOR + 1)]
                    vl = 0.0 if b - Le <= FLOOR else Vf[b - Le - (FLOOR + 1)]
                    v = p * vw + (1 - p) * vl
                    if v > best + 1e-12:
                        best, act = v, (W, Le)
            nVf[i] = best; npf[i] = act
        Ve, Vf, pe, pf = nVe, nVf, npe, npf
    return pe, pf, float(Ve[0 - (FLOOR + 1)]), float(Vf[0 - (FLOOR + 1)])


def main() -> int:
    out = {}
    for H in (84, 252):
        pe, pf, ppass, vf = solve(H)
        ev = ppass * vf - FEE_PCT
        out[H] = {"p_pass": ppass, "funded_value_pct": vf * 100, "ev_per_attempt_pct": ev * 100, "ev_per_10k": ev * 10_000,
                  "eval_start_action": [int(x) for x in pe[0 - (FLOOR + 1)]], "funded_start_action": [int(x) for x in pf[0 - (FLOOR + 1)]]}
        print(f"H {H}: P(pass) {ppass:.1%}, funded value {vf*100:.2f}% of the account, EV per attempt {ev*100:+.2f}% (${ev*10_000:+,.0f} per $10K); "
              f"start actions eval (take, stop units) {out[H]['eval_start_action']}, funded {out[H]['funded_start_action']}", flush=True)
    (ROOT / "reports" / "a78_crypto_prop.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def day_paths():
    z = np.load(ROOT / "data" / "crypto" / "btc_1h.npz"); ts = z["ts"]; days = {}
    for i, t in enumerate(ts):
        d = dt.datetime.fromtimestamp(int(t), dt.timezone.utc)
        days.setdefault(d.date(), {})[d.hour] = i
    D, H, L, C = [], [], [], []
    for d in sorted(days):
        hs = days[d]
        if len(hs) < 23 or 0 not in hs:
            continue
        o = z["o"][hs[0]]; idx = [hs[h] for h in range(24) if h in hs]
        D.append(d); H.append(z["h"][idx] / o - 1); L.append(z["l"][idx] / o - 1); C.append(z["c"][idx] / o - 1)
    T = max(len(x) for x in C)
    pad = lambda a: np.array([np.r_[x, np.repeat(x[-1], T - len(x))] for x in a])
    return D, pad(H), pad(L), pad(C)


def replay(pe, pf, D, Hh, Ll, Cc, window: int, seed: int):
    rng = np.random.default_rng(seed); side = np.where(rng.random(len(D)) < 0.5, 1.0, -1.0)
    h = np.where(side[:, None] > 0, Hh, -Ll); l = np.where(side[:, None] > 0, Ll, -Hh); c = side[:, None] * Cc
    S = len(D); starts = np.arange(0, S - window); A = len(starts)
    ev = np.ones(A, bool); b = np.zeros(A); fees = np.full(A, FEE_PCT); paid = np.zeros(A); evals = np.ones(A); low = np.full(A, -FEE_PCT)
    for d in range(window):
        idx = starts + d
        bu = np.clip(np.rint(b / U).astype(int), FLOOR + 1, TARGET - 1)
        act = np.where(ev[:, None], pe[bu - (FLOOR + 1)], pf[np.minimum(bu, 0) - (FLOOR + 1)])
        W = act[:, 0] * U; Lr = act[:, 1] * U; trade = act[:, 1] > 0
        N = Lr / STOP_DIST; cost = N * 2 * COST_SIDE
        Ns = np.where(trade, N, 1.0)
        tw = (W + cost) / Ns; tl = np.maximum(Lr - cost, 1e-9) / Ns
        hit_w = h[idx] >= tw[:, None]; hit_l = l[idx] <= -tl[:, None]; big = h.shape[1] + 1
        iw = np.where(hit_w.any(1), hit_w.argmax(1), big); il = np.where(hit_l.any(1), hit_l.argmax(1), big)
        stop = (il < big) & (il <= iw); take = (iw < big) & ~stop
        pnl = np.where(stop, -Lr, np.where(take, W, N * c[idx, -1] - cost))
        b = b + np.where(trade, pnl, 0.0)
        dead = b <= FLOOR * U + 1e-12
        passed = ev & ~dead & (b >= TARGET * U - 1e-12)
        wd = np.where(~ev & ~dead & (b > 0), b, 0.0); paid += SPLIT * wd; b = b - wd
        ev = np.where(passed, False, ev); b = np.where(passed, 0.0, b)
        rebuy = dead & (d + 1 < window)
        fees += np.where(rebuy, FEE_PCT, 0.0); evals += rebuy; ev = np.where(dead, True, ev); b = np.where(dead, 0.0, b)
        low = np.minimum(low, paid - fees)
    return paid - fees, paid, evals, low, np.array(D)[starts]


def replay_main() -> int:
    out = json.loads((ROOT / "reports" / "a78_crypto_prop.json").read_text())
    D, Hh, Ll, Cc = day_paths(); print(len(D), "BTC days", D[0], "->", D[-1], flush=True)
    for H in (84, 252):
        pe, pf, ppass, vf = solve(H); res = {}
        nets = [replay(pe, pf, D, Hh, Ll, Cc, H, s) for s in range(6)]
        net = np.concatenate([x[0] for x in nets]); low = np.concatenate([x[3] for x in nets]); ev_n = np.concatenate([x[2] for x in nets])
        st = nets[0][4]; m21 = np.tile(np.array([x >= dt.date(2021, 1, 1) for x in st]), 6)
        for lab, m in (("all starts", np.ones(len(net), bool)), ("2021+ starts", m21)):
            x = net[m] * 10_000
            res[lab] = {"mean_per_10k": float(x.mean()), "median": float(np.median(x)), "p_pos": float((x > 0).mean()), "p10": float(np.percentile(x, 10)),
                        "evals": float(ev_n[m].mean()), "cash_low_p95": float(-np.percentile(low[m], 5) * 10_000)}
            print(f"  window {H} days, {lab}: per $10K mean ${x.mean():+,.0f} median ${np.median(x):+,.0f} P>0 {(x > 0).mean():.0%} p10 ${np.percentile(x, 10):+,.0f} | "
                  f"evaluations {ev_n[m].mean():.1f} | cash low 95% ${res[lab]['cash_low_p95']:,.0f}", flush=True)
        out[str(H)]["replay_random_sides"] = res
    (ROOT / "reports" / "a78_crypto_prop.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


SWAP_DAY = 0.0003                            # perpetual funding / swap, of notional a day (held positions)


def hourly():
    z = np.load(ROOT / "data" / "crypto" / "btc_1h.npz")
    return z["ts"], z["o"], z["h"], z["l"], z["c"]


def replay_hold(pe, pf, window_days: int, seed: int, step_days: int = 3):
    """Each trade held until its take or stop (crypto trades around the clock), side random; back-to-back accounts from a start every
    step_days; returns per-start (net, paid, evaluations, cash low, start time) as fractions of the account."""
    ts, o, h, l, c = hourly(); n = len(ts); rng = np.random.default_rng(seed)
    cmax_cache = None
    starts = list(range(0, n - window_days * 24, step_days * 24)); res = []
    for s0 in starts:
        end = s0 + window_days * 24; t = s0; ev = True; b = 0.0; fees = FEE_PCT; paid = 0.0; evals = 1; low = -FEE_PCT
        while t < end - 1:
            bu = int(np.clip(round(b / U), FLOOR + 1, TARGET - 1))
            W_, L_ = (pe if ev else pf)[(bu if ev else min(bu, 0)) - (FLOOR + 1)]
            W, Lr = W_ * U, L_ * U; N = Lr / STOP_DIST; cost = N * 2 * COST_SIDE
            sd = 1.0 if rng.random() < 0.5 else -1.0; p0 = o[t]
            tw = (W + cost) / N; tl = max(Lr - cost, 1e-9) / N
            hh = (h[t:end] / p0 - 1) * sd; ll = (l[t:end] / p0 - 1) * sd
            if sd < 0:
                hh, ll = ll, hh
            iw = np.argmax(hh >= tw) if (hh >= tw).any() else None; il = np.argmax(ll <= -tl) if (ll <= -tl).any() else None
            if il is not None and (iw is None or il <= iw):
                k = il; pnl = -Lr
            elif iw is not None:
                k = iw; pnl = W
            else:
                k = end - 1 - t; pnl = N * sd * (c[end - 1] / p0 - 1) - cost
            pnl -= N * SWAP_DAY * (k + 1) / 24
            b += pnl; t += k + 1
            if b <= FLOOR * U + 1e-12:
                if t < end - 1:
                    fees += FEE_PCT; evals += 1
                ev, b = True, 0.0
            elif ev and b >= TARGET * U - 1e-12:
                ev, b = False, 0.0
            elif not ev and b > 0:
                paid += SPLIT * b; b = 0.0
            low = min(low, paid - fees)
        res.append((paid - fees, paid, evals, low, ts[s0]))
    return res


def hold_main() -> int:
    out = json.loads((ROOT / "reports" / "a78_crypto_prop.json").read_text())
    for H in (84, 252):
        pe, pf, ppass, vf = solve(H); ev_ = ppass * vf - FEE_PCT
        print(f"H {H} (always trade): P(pass) {ppass:.1%}, funded value {vf*100:.2f}%, EV per attempt {ev_*100:+.2f}% (${ev_*10_000:+,.0f} per $10K)", flush=True)
        for mode in ("daily exit", "hold to bracket"):
            if mode == "daily exit":
                D, Hh, Ll, Cc = day_paths(); rr = [replay(pe, pf, D, Hh, Ll, Cc, H, s) for s in range(6)]
                net = np.concatenate([x[0] for x in rr]); evn = np.concatenate([x[2] for x in rr]); low = np.concatenate([x[3] for x in rr])
            else:
                rr = [r for s in range(6) for r in replay_hold(pe, pf, H, s)]
                net = np.array([r[0] for r in rr]); evn = np.array([r[2] for r in rr]); low = np.array([r[3] for r in rr])
            x = net * 10_000
            row = {"mean_per_10k": float(x.mean()), "median": float(np.median(x)), "p_pos": float((x > 0).mean()), "p10": float(np.percentile(x, 10)),
                   "p90": float(np.percentile(x, 90)), "evals": float(evn.mean()), "cash_low_p95": float(-np.percentile(low, 5) * 10_000)}
            out.setdefault(f"{H}_always_trade", {"p_pass": ppass, "funded_value_pct": vf * 100, "ev_pct": ev_ * 100})[mode] = row
            print(f"  {H} days, {mode:15}: per $10K mean ${row['mean_per_10k']:+,.0f} median ${row['median']:+,.0f} P>0 {row['p_pos']:.0%} p10 ${row['p10']:+,.0f} "
                  f"p90 ${row['p90']:+,.0f} | evaluations {row['evals']:.1f} | cash low 95% ${row['cash_low_p95']:,.0f}", flush=True)
    (ROOT / "reports" / "a78_crypto_prop.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0
