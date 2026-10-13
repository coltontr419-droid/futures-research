"""A23 - Tradeify's 100K and 150K accounts (Daily and Flex) against the 50K: the A01 staking game re-solved for each
account's rules, then replayed on the five live markets and soybeans, alone and as a five-account book. A COMPUTATION;
zero edge; no trial. decisions.md 145.

    python -m futuresres.reporting.a23_account_sizes --check            (the 50K spec reproduces the live engine)
    python -m futuresres.reporting.a23_account_sizes --solve            (game values for every spec)
    python -m futuresres.reporting.a23_account_sizes --replay ERA       (per-start nets, every market x spec)
    python -m futuresres.reporting.a23_account_sizes --book             (five-account books, all size mixes)

RULES (the user, 2026-10-12). Evaluation: 100K target $6,000, EOD trailing drawdown $3,000; 150K $9,000, $4,500; no daily loss
limit; consistency 40% (50% for an add-on, price not given - the break-even add-on price is reported). Fees $265 / $369 less the
standing 30% sale = $185.50 / $258.30; the 50K at the user's $80. Funded DAILY: 100K drawdown $2,500 locking at $100,000, daily
loss $1,250, $1,750 a payout; 150K $3,500, $1,750, $2,500. Funded FLEX: 100K drawdown $3,000 locking at $100,000, no daily loss
limit, $3,500 a payout once every 5 winning days (a day >= $200); 150K $4,500, $4,500, (>= $250). All: payouts from profit
above the lock point, capped until the 3rd payout ("live" after), 90% split, no consistency once funded; at most 5 accounts of
any size at once. The 50K Daily is the live plan's game (decisions.md 93, 136).

SCALING, fixed before any result: $100 units throughout. Take menu = A01's W_SET joined with W_SET x (target / $3,000); stop
menu = the live plan's stops (5, 6, 8, 10) x (drawdown / $2,000) for each phase, capped at the daily loss limit where there
is one. Contracts per market = the 50K plan's x (evaluation drawdown / $2,000), rounded half up (MNQ 4 -> 6 -> 9, MGC 8 -> 12
-> 18, MCL 10 -> 15 -> 23, NKD 1 -> 2 -> 2, FDXM 2 -> 3 -> 5, ZS 3 -> 5 -> 7). Policies: the stationary policy at day 21
(evaluation: max P(pass); funded: max E[$]), as the live plan.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import sys
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data" / "cache"
BASE_W = tuple(range(1, 16)) + (18, 20, 25, 30)
BASE_L = (5, 6, 8, 10)
HORIZON = 84


@dataclass(frozen=True)
class Spec:
    name: str
    start: float
    fee: float
    target: int          # $100 units
    dd: int
    cons: float
    f_dd: int            # funded drawdown = lock distance = payout buffer
    f_cap: int           # per-payout cap before live
    f_daily: int | None  # funded daily loss limit (units) or None
    flex_thr: int | None = None      # Flex: winning-day threshold ($); None = Daily payouts
    e_daily: int | None = None       # evaluation daily loss limit (units)
    live_after: int = 3
    k_contracts: float = field(default=1.0)
    cap_usd: float = 0.0             # the real per-payout cap in $ (the game uses whole $100 units)
    cost: float = 0.0                # A24: round trip $ per trade priced into the odds, p = (L - c) / (W + L); 0 = A01's fair coin
    he: int = 21                     # A24: evaluation horizon (days) the policy is solved for
    hf: int = 21                     # A24: funded horizon (days)
    withdraw: str = "all"            # A25: "all" = take everything allowed each day (the plan); "choose" = none / half / all

    @property
    def w_set(self) -> tuple:
        k = self.target / 30
        return tuple(sorted(set(BASE_W) | {int(math.floor(w * k + 0.5)) for w in BASE_W}))

    @property
    def l_eval(self) -> tuple:
        s = sorted({int(math.floor(l * self.dd / 20 + 0.5)) for l in BASE_L})
        return tuple(min(l, self.e_daily) for l in s) if self.e_daily else tuple(s)

    @property
    def l_funded(self) -> tuple:
        s = sorted({int(math.floor(l * self.f_dd / 20 + 0.5)) for l in BASE_L})
        return tuple(sorted({min(l, self.f_daily) for l in s})) if self.f_daily else tuple(s)


def specs(cons_100_150: float = 0.40) -> dict:
    c = cons_100_150
    return {
        "50K Daily": Spec("50K Daily", 50_000, 80.0, 30, 20, 0.40, 20, 12, 10, e_daily=10, k_contracts=1.0, cap_usd=1250.0),
        "100K Daily": Spec("100K Daily", 100_000, 185.50, 60, 30, c, 25, 17, 12, k_contracts=1.5, cap_usd=1750.0),
        "150K Daily": Spec("150K Daily", 150_000, 258.30, 90, 45, c, 35, 25, 17, k_contracts=2.25, cap_usd=2500.0),
        "100K Flex": Spec("100K Flex", 100_000, 185.50, 60, 30, c, 30, 35, None, flex_thr=200, k_contracts=1.5, cap_usd=3500.0),
        "150K Flex": Spec("150K Flex", 150_000, 258.30, 90, 45, c, 45, 45, None, flex_thr=250, k_contracts=2.25, cap_usd=4500.0),
    }


# ------------------------------------------------------------------ the game
def solve_eval(s: Spec, days: int = 21) -> tuple[np.ndarray, dict, float]:
    """A01's evaluation game for spec s; returns (policy at `days`, (B_MIN, B_MAX, BD_MAX), P(pass within days))."""
    B_MIN, B_MAX = -s.dd, int(s.target * 1.5)
    BD_MAX = int(math.ceil(s.cons * B_MAX))
    nb = B_MAX - B_MIN + 1
    b = np.arange(nb)[:, None, None] + B_MIN
    pk = np.arange(B_MAX + 1)[None, :, None]
    bd = np.arange(BD_MAX + 1)[None, None, :]
    shape = (nb, B_MAX + 1, BD_MAX + 1)
    B, PK, BD = (np.broadcast_to(x, shape) for x in (b, pk, bd))
    valid = (PK >= np.maximum(B, 0)) & (B > PK - s.dd)
    V = np.zeros(shape); act = np.zeros(shape, np.int32)
    for t in range(1, days + 1):
        newV = np.full(shape, -1.0); act = np.zeros(shape, np.int32)
        for W in s.w_set:
            bw = np.minimum(B + W, B_MAX); pkw = np.maximum(PK, bw); bdw = np.minimum(np.maximum(BD, W), BD_MAX)
            win_pass = (bw >= s.target) & (np.maximum(BD, W) <= s.cons * bw)
            vw = np.where(win_pass, 1.0, V[bw - B_MIN, pkw, bdw])
            dist = B - (PK - s.dd)
            for L in s.l_eval:
                Le = np.minimum(L, dist); p = np.clip(Le - s.cost / 100, 0, None) / (W + Le)
                bl = B - Le; fail = bl <= PK - s.dd
                vl = np.where(fail, 0.0, V[np.clip(bl, B_MIN, B_MAX) - B_MIN, PK, BD])
                val = p * vw + (1 - p) * vl
                better = val > newV + 1e-12
                newV = np.where(better, val, newV); act = np.where(better, W * 100 + L, act)
        V = np.where(valid, newV, 0.0)
    return act, {"B_MIN": B_MIN, "B_MAX": B_MAX, "BD_MAX": BD_MAX}, float(V[0 - B_MIN, 0, 0])


def solve_funded(s: Spec, days: int = 21) -> tuple[np.ndarray, dict, float]:
    """A01's funded game (max E[$ paid, 90%] within `days`) for spec s; Flex adds the winning-day count (0..5)."""
    BUF = s.f_dd; FMIN, FMAX = -s.f_dd, BUF + max(s.w_set) + 10          # 50K: 60, as a01
    WD = 5 if s.flex_thr else 0
    nb = FMAX - FMIN + 1; L_ = s.live_after
    shape = (nb, BUF + 1, L_ + 1, WD + 1)
    B = np.broadcast_to((np.arange(nb) + FMIN)[:, None, None, None], shape)
    PK = np.broadcast_to(np.arange(BUF + 1)[None, :, None, None], shape)
    N = np.broadcast_to(np.arange(L_ + 1)[None, None, :, None], shape)
    WC = np.broadcast_to(np.arange(WD + 1)[None, None, None, :], shape)
    floor = np.where(PK >= BUF, 0, PK - s.f_dd)
    valid = (B > floor) & (PK >= np.minimum(np.maximum(B, 0), BUF))

    CODES = (2,) if s.withdraw == "all" else (0, 1, 2)          # 0 none, 1 half, 2 all of what may be withdrawn today

    def eod(bb, pkk, wcc, Vn):
        """End of day after the trade: value of the best withdrawal (and its code) from balance bb, peak pkk (updated),
        winning-day count wcc, with tomorrow's values Vn."""
        elig = (wcc >= WD) if WD else True
        ex = np.where(elig, np.clip(bb - BUF, 0, None), 0)
        full = np.where(N >= L_, ex, np.minimum(ex, s.f_cap))
        bestv = np.full(shape, -1.0); code = np.zeros(shape, np.int8)
        for c_ in CODES:
            amt = full if c_ == 2 else ((full + 1) // 2 if c_ == 1 else 0 * full)
            n2 = np.where(amt > 0, np.minimum(N + 1, L_), N)
            wc3 = np.where(amt > 0, 0, wcc) if WD else WC
            v = amt * 90.0 + Vn[bb - amt - FMIN, pkk, n2, wc3]
            better = v > bestv + 1e-12
            bestv = np.where(better, v, bestv); code = np.where(better, c_, code)
        return bestv, code

    V = np.zeros(shape); act = np.zeros(shape, np.int32); wpol = np.full(shape, 2, np.int8)
    for t in range(1, days + 1):
        best = np.full(shape, -1.0); act = np.zeros(shape, np.int32)
        if s.withdraw != "all":                       # today's end-of-day withdrawal rule, on the whole grid
            _, wpol = eod(B, np.minimum(np.maximum(PK, np.clip(B, 0, None)), BUF), WC, V)
        for W in s.w_set:
            won = int(WD > 0 and W * 100 >= s.flex_thr)
            bw = np.minimum(B + W, FMAX)
            rw, _ = eod(bw, np.minimum(np.maximum(PK, np.clip(bw, 0, None)), BUF), np.minimum(WC + won, WD) if WD else WC, V)
            for L in s.l_funded:
                Le = np.minimum(L, np.maximum(B - floor, 1)); p = np.clip(Le - s.cost / 100, 0, None) / (W + Le)
                bl = np.clip(B - Le, FMIN, FMAX); failL = (B - Le) <= floor
                rl, _ = eod(bl, np.minimum(np.maximum(PK, np.clip(bl, 0, None)), BUF), WC, V)
                rl = np.where(failL, 0.0, rl)
                val = np.where(valid, p * rw + (1 - p) * rl, 0.0)
                better = val > best + 1e-12
                best = np.where(better, val, best); act = np.where(better, W * 100 + L, act)
        V = np.where(valid, np.maximum(best, 0.0), 0.0)
    return act, {"FMIN": FMIN, "FMAX": FMAX, "BUF": BUF, "WD": WD, "WPOL": wpol}, float(V[0 - FMIN, 0, 0, 0])


_POL: dict = {}


def policy(s: Spec):
    if s not in _POL:
        pe, ge, v_e = solve_eval(s, s.he); pf, gf, v_f = solve_funded(s, s.hf)
        _POL[s] = (pe, ge, v_e, pf, gf, v_f)
    return _POL[s]


# ------------------------------------------------------------------ the replay
def _bracket(h, l, c, W, L):
    A, T = c.shape
    hitW = h >= W[:, None]; hitL = l <= -L[:, None]; big = T + 1
    tw = np.where(hitW.any(1), hitW.argmax(1), big); tl = np.where(hitL.any(1), hitL.argmax(1), big)
    out = c[:, -1].copy(); stop = (tl < big) & (tl <= tw); take = (tw < big) & ~stop
    out[stop] = -L[stop]; out[take] = W[take]            # stops fill at the stop price (the live plan's assumption)
    return out


def replay(s: Spec, paths: tuple, n: int, rt: float, window: int = HORIZON) -> dict:
    """Back-to-back attempts from every start date, real sessions in order (a02_real.sequential 'replay', per trader),
    under spec s, with one-contract GROSS $ paths (h, l, c), n contracts, round trip rt each."""
    pe, ge, _, pf, gf, _ = policy(s)
    h1, l1, c1 = paths
    h, l, c = h1 * np.float32(n), l1 * np.float32(n), c1 * np.float32(n)
    cost = rt * n; S = len(c); starts = np.arange(0, S - window); A = len(starts)
    START, ddE, ddF = s.start, s.dd * 100.0, s.f_dd * 100.0
    phase = np.zeros(A, int); eq = np.full(A, START); pk = eq.copy(); best = np.zeros(A); npay = np.zeros(A, int); wc = np.zeros(A, int)
    fees = np.full(A, s.fee); paid = np.zeros(A); first = np.full(A, -1)
    for d in range(window):
        idx = starts + d; ev = phase == 0; fu = ~ev
        b_e = np.clip(np.rint((eq - START) / 100).astype(int), ge["B_MIN"], ge["B_MAX"])
        pk_e = np.maximum(np.clip(np.rint((pk - START) / 100).astype(int), 0, ge["B_MAX"]), np.maximum(b_e, 0))
        bd_e = np.clip(np.rint(best / 100).astype(int), 0, ge["BD_MAX"])
        a_e = pe[b_e - ge["B_MIN"], pk_e, bd_e]
        b_f = np.clip(np.rint((eq - START) / 100).astype(int), gf["FMIN"], gf["FMAX"])
        pk_f = np.maximum(np.clip(np.rint((pk - START) / 100).astype(int), 0, gf["BUF"]), np.clip(b_f, 0, gf["BUF"]))
        a_f = pf[b_f - gf["FMIN"], pk_f, np.minimum(npay, s.live_after), np.minimum(wc, gf["WD"])]
        a = np.where(ev, a_e, a_f)
        W = (a // 100) * 100.0; L = (a % 100) * 100.0
        floor = np.where(ev, pk - ddE, np.where(pk >= START + ddF, START, pk - ddF))
        L = np.minimum(L, np.maximum(eq - floor - 1, 1))
        # the playbook (decisions.md 113): within one day's costs (+$10) of the floor the account is FINISHED - any trade
        # breaches it - and is replaced by a new evaluation. (a02_real reaches nearly the same end through its 2.32 engine cost.)
        trade = (a > 0) & (eq - floor > cost + 10)
        pnl = _bracket(h[idx], l[idx], c[idx], np.where(trade, W + cost, 1e12), np.where(trade, np.maximum(L - cost, 1.0), 1e12))
        # P&L to the cent: float32 paths made a +$600 take land at $599.99, so an account at exactly the target failed to
        # pass (found on crude, decisions.md 146); the live engine's 2.32 offsets happened to avoid it.
        pnl = np.round(np.where(trade, pnl.astype(np.float64) - cost, 0.0), 2)
        ne = eq + pnl; br = (ne <= floor) | ~trade
        eq = ne; pk = np.maximum(pk, ne)
        best = np.where(ev, np.maximum(best, pnl), best)
        prof = eq - START
        ok = ev & ~br & (prof >= s.target * 100 - 0.005) & (best <= s.cons * prof + 0.005)
        if s.flex_thr:
            wc = np.where(fu & (pnl >= s.flex_thr), wc + 1, wc)
            elig = wc >= 5
        else:
            elig = np.ones(A, bool)
        amt = np.where(fu & ~br & elig, np.maximum(eq - (START + ddF), 0.0), 0.0)
        amt = np.where(npay >= s.live_after, amt, np.minimum(amt, s.cap_usd or s.f_cap * 100.0))
        if s.withdraw != "all":                       # A25: the solver's end-of-day choice - none, half or all
            bb = np.clip(np.rint((eq - START) / 100).astype(int), gf["FMIN"], gf["FMAX"])
            pkk = np.minimum(np.clip(np.rint((pk - START) / 100).astype(int), 0, gf["BUF"]), gf["BUF"])
            pkk = np.maximum(pkk, np.clip(bb, 0, gf["BUF"]))
            code = gf["WPOL"][bb - gf["FMIN"], pkk, np.minimum(npay, s.live_after), np.minimum(wc, gf["WD"])]
            amt = np.where(code == 2, amt, np.where(code == 1, np.round(amt / 2, 2), 0.0))
        got = amt > 0
        paid += 0.9 * amt; first = np.where(got & (first < 0), d + 1, first)
        eq -= amt; npay += got; wc = np.where(got, 0, wc)
        reset = br | ok
        new_phase = np.where(ok, 1, np.where(br, 0, phase))
        eq = np.where(reset, START, eq); pk = np.where(reset, START, pk)
        best = np.where(reset, 0.0, best); npay = np.where(reset, 0, npay); wc = np.where(reset, 0, wc)
        fees += np.where(br & (d + 1 < window), s.fee, 0.0)
        phase = new_phase
    return {"start": starts, "net": paid - fees, "first": first, "fees": fees, "paid": paid}


# ------------------------------------------------------------------ markets
#: market -> (50K contracts, round trip)
MARKETS = {"MNQ": (4, 2.32), "MGC": (8, 3.32), "MCL": (10, 3.32), "NKD": (1, 4.0), "FDXM": (2, 4.0), "ZS": (3, 4.5)}


def contracts(market: str, s: Spec) -> int:
    return int(math.floor(MARKETS[market][0] * s.k_contracts + 0.5))


def market_paths(market: str, era: str):
    """One-contract GROSS $ paths (h, l, c) and session dates."""
    if market in ("MNQ", "MGC"):
        import futuresres.reporting.a08_gold as a8
        win = {"MNQ": "rth_0930_1600", "MGC": "london_0300_1130"}[market]
        h, l, c, d = a8.era_paths(era, market, win)
        return (h, l, c), np.asarray(d).astype("datetime64[D]")
    if market == "MCL":                  # one daily bar -> 3 points (the extreme nearer the entry first, a15's rule)
        import futuresres.reporting.a15_crude as c15
        from futuresres.reporting.a22_more_markets import points
        h, l, c, d = c15.mcl_paths(era)
        p = points(np.zeros_like(c), h, l, c).astype(np.float32)
        return (p, p, p), d.astype("datetime64[D]")
    if market in ("NKD", "FDXM"):
        import futuresres.reporting.a21_more_accounts as a21
        h, l, c, d = a21.paths("DAX" if market == "FDXM" else "NKD", era)
        return (h, l, c), d.astype("datetime64[D]")
    if market == "ZS":
        import futuresres.reporting.a22_more_markets as a22
        p, d = a22.long_paths("ZS", era)
        return (p, p, p), d
    raise KeyError(market)


def check() -> dict:
    """The 50K spec must reproduce the live engine (a02_real.sequential 'replay', level fills, live policy) on MNQ and MGC."""
    import futuresres.reporting.a12_joint as j
    import futuresres.reporting.a21_more_accounts as a21
    import futuresres.reporting.a02_real as a2
    warnings.filterwarnings("ignore")
    a21._policy(); a2.STOP_FILL = "level"
    s = specs()["50K Daily"]; out = {}
    for m in ("MNQ", "MGC"):
        ref = j.per_start("post", m)
        (h, l, c), d = market_paths(m, "post")
        mine = replay(s, (h, l, c), MARKETS[m][0], MARKETS[m][1])
        out[m] = {"live_engine_mean_net": float(ref["net"].mean()), "a23_mean_net": float(mine["net"].mean()),
                  "live_p_payout": float((ref["first"] > 0).mean()), "a23_p_payout": float((mine["first"] > 0).mean())}
        print(m, out[m], flush=True)
    return out


def solve_report() -> dict:
    out = {}
    for cons in (0.40, 0.50):
        for name, s in specs(cons).items():
            if cons == 0.50 and name == "50K Daily":
                s = Spec("50K Daily", 50_000, 80.0, 30, 20, 0.50, 20, 12, 10, e_daily=10, cap_usd=1250.0)
            t0 = time.time(); pe, ge, v_e, pf, gf, v_f = policy(s)
            out[f"{name} cons {cons:.0%}"] = {"p_pass_21": v_e, "funded_E_paid_21": v_f, "fee": s.fee,
                                              "w_set": list(s.w_set), "l_eval": list(s.l_eval), "l_funded": list(s.l_funded)}
            print(f"{name:11} cons {cons:.0%}: P(pass within 21 days) {v_e:.3f}; funded E[$ in 21 days] ${v_f:,.0f}; fee ${s.fee:.2f} "
                  f"({time.time()-t0:.0f}s)", flush=True)
    return out


def replay_era(era: str) -> None:
    warnings.filterwarnings("ignore")
    res = {}
    for cons in (0.40, 0.50):
        sp = specs(cons)
        if cons == 0.50:
            sp["50K Daily"] = Spec("50K Daily", 50_000, 80.0, 30, 20, 0.50, 20, 12, 10, e_daily=10, cap_usd=1250.0)
        for m in MARKETS:
            (h, l, c), d = market_paths(m, era)
            for name, s in sp.items():
                n = contracts(m, s)
                r = replay(s, (h, l, c), n, MARKETS[m][1])
                key = f"{m}|{name}|{cons:.2f}"
                res[key] = {"date": d[r["start"]].astype(str).tolist(), "net": r["net"].round(2).tolist(),
                            "first": r["first"].tolist(), "fees": r["fees"].round(2).tolist()}
                print(f"{era} {m:4} {name:11} cons {cons:.0%} {n:2} contracts: P(payout) {(r['first'] > 0).mean():.0%} "
                      f"mean net {r['net'].mean():+8,.0f} P(net>0) {(r['net'] > 0).mean():.0%} fees {r['fees'].mean():6,.0f}", flush=True)
            del h, l, c
    (CACHE / f"a23_replay_{era}.json").write_text(json.dumps(res))


def book() -> dict:
    """Five-account books on common start dates: every assignment of a size/type to each of the five live markets
    (and soybeans in place of crude), per era; the best books and the all-one-size books."""
    import itertools
    out = {}
    for era in ("pre", "post"):
        R = json.loads((CACHE / f"a23_replay_{era}.json").read_text())
        out[era] = {}
        for cons in ("0.40", "0.50"):
            for five in (("MNQ", "MGC", "MCL", "NKD", "FDXM"), ("MNQ", "MGC", "ZS", "NKD", "FDXM")):
                names = sorted({k.split("|")[1] for k in R})
                common = None
                for m in five:
                    for nm in names:
                        ds = set(R[f"{m}|{nm}|{cons}"]["date"])
                        common = ds if common is None else common & ds
                common = sorted(common)
                sel = {}
                for m in five:
                    for nm in names:
                        r = R[f"{m}|{nm}|{cons}"]; ix = {dd: i for i, dd in enumerate(r["date"])}
                        ii = [ix[dd] for dd in common]
                        sel[(m, nm)] = {k: np.array(r[k])[ii] for k in ("net", "first", "fees")}
                rows = []
                for combo in itertools.product(names, repeat=len(five)):
                    net = sum(sel[(m, nm)]["net"] for m, nm in zip(five, combo))
                    fees = sum(sel[(m, nm)]["fees"] for m, nm in zip(five, combo))
                    rows.append({"book": dict(zip(five, combo)), "mean_net": float(net.mean()), "median_net": float(np.median(net)),
                                 "p_net_positive": float((net > 0).mean()), "net_p10": float(np.quantile(net, 0.1)),
                                 "worst": float(net.min()), "mean_fees": float(fees.mean()), "fees_p90": float(np.quantile(fees, 0.9))})
                rows.sort(key=lambda r: -r["mean_net"])
                uniform = [r for r in rows if len(set(r["book"].values())) == 1]
                label = f"cons {cons} | {'+'.join(five)}"
                out[era][label] = {"common_starts": len(common), "first": common[0], "last": common[-1],
                                   "uniform": uniform, "top10": rows[:10],
                                   "per_market": {f"{m}|{nm}": {"mean_net": float(sel[(m, nm)]["net"].mean()),
                                                                "p_payout": float((sel[(m, nm)]["first"] > 0).mean())}
                                                  for m in five for nm in names}}
                print(f"== {era} {label}: {len(common)} starts {common[0]} -> {common[-1]}", flush=True)
                for r in uniform:
                    print(f"   all {list(r['book'].values())[0]:11}: mean {r['mean_net']:+8,.0f} median {r['median_net']:+8,.0f} "
                          f"P(net>0) {r['p_net_positive']:.0%} p10 {r['net_p10']:+8,.0f} fees {r['mean_fees']:6,.0f} (p90 {r['fees_p90']:,.0f})", flush=True)
                for r in rows[:5]:
                    print(f"   best {r['book']}: mean {r['mean_net']:+8,.0f} P(net>0) {r['p_net_positive']:.0%} p10 {r['net_p10']:+8,.0f} "
                          f"fees {r['mean_fees']:6,.0f}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true"); ap.add_argument("--solve", action="store_true")
    ap.add_argument("--replay"); ap.add_argument("--book", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        (ROOT / "reports" / "a23_check.json").write_text(json.dumps(check(), indent=1) + "\n")
    if a.solve:
        (ROOT / "reports" / "a23_solve.json").write_text(json.dumps(solve_report(), indent=1) + "\n")
    if a.replay:
        replay_era(a.replay)
    if a.book:
        (ROOT / "reports" / "a23_book.json").write_text(json.dumps(book(), indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
