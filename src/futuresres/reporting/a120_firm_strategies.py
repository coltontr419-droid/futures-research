"""A120 (decisions.md 1088): a strategy fitted to EACH prop firm's own rules, at zero edge. No trial.

The Tradeify plan (one large bracket a day) fails firms with consistency / qualifying-day payout gates (§766). Here each firm gets its
own fixed daily bracket (take W, stop L in $; evaluation and funded stages separately), traded once a day on MNQ RTH paths
(one-contract $ paths, A23) with the side randomised every day (no market edge), and the firm's 2026 rules applied to end-of-day
balances: evaluation target / trailing drawdown / consistency / daily loss limit / fees (monthly or one-time + activation); funded
trailing drawdown and lock, payout gates (N qualifying days >= $q, best-day consistency, buffer, positive since last payout), payout
size (cap ladder, share of profit or balance, minimum), split, payout count limit, Topstep's post-payout floor. A failed or finished
account is replaced at once (a new fee). Value = mean (payouts x split - fees) per 84-session run, one account slot.

Selection on 2010-20 paths, read on 2021-26 (and the reverse), so a policy chosen for one era is scored on the other.

    python -m futuresres.reporting.a120_firm_strategies
"""

from __future__ import annotations

import itertools
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23

ROOT = Path(__file__).resolve().parents[3]
RT = 2.32                                   # MNQ round trip per contract (A23)
H = 84                                      # sessions per run
SEEDS = (11, 12, 13, 14)

#: rules per firm (50K). Monetary amounts relative to the $50,000 start. Sources and doubts in decisions.md 1088.
FIRMS = {
    "Tradeify Select Daily (ref)": dict(
        e_fee=116.0, e_month=0.0, act=0.0, e_target=3000, e_dd=2000, e_cons=0.40, e_cons_of="profit", e_dll=None, e_min_days=1,
        f_dd=2000, f_lock=0, q_days=0, q_amt=0, f_cons=None, buffer=2000, pay_frac=None, caps=[1250], cap_rule="v2", pmin=250,
        split=0.9, max_pay=99, floor_after_pay=None),
    "Topstep XFA Standard": dict(
        e_fee=0.0, e_month=49.0, act=149.0, e_target=3000, e_dd=2000, e_cons=0.50, e_cons_of="target", e_dll=None, e_min_days=2,
        f_dd=2000, f_lock=0, q_days=5, q_amt=150, f_cons=None, buffer=0, pay_frac=0.5, caps=[2000], cap_rule="frac_balance", pmin=125,
        split=0.9, max_pay=99, floor_after_pay=0),
    "Topstep XFA Consistency": dict(
        e_fee=0.0, e_month=49.0, act=149.0, e_target=3000, e_dd=2000, e_cons=0.50, e_cons_of="target", e_dll=None, e_min_days=2,
        f_dd=2000, f_lock=0, q_days=3, q_amt=0.01, f_cons=0.40, buffer=0, pay_frac=0.5, caps=[3000], cap_rule="frac_balance", pmin=125,
        split=0.9, max_pay=99, floor_after_pay=0),
    "Apex EOD (list $349+$119)": dict(
        e_fee=349.0, e_month=0.0, act=119.0, e_target=3000, e_dd=2000, e_cons=None, e_cons_of="profit", e_dll=1000, e_min_days=1,
        f_dd=2000, f_lock=100, q_days=5, q_amt=250, f_cons=0.50, buffer=2100, pay_frac=None, caps=[1500, 1500, 2000, 2500, 2500, 3000],
        cap_rule="above_buffer", pmin=500, split=1.0, max_pay=6, floor_after_pay=None),
    "Apex EOD (80% off: $70+$119)": dict(
        e_fee=70.0, e_month=0.0, act=119.0, e_target=3000, e_dd=2000, e_cons=None, e_cons_of="profit", e_dll=1000, e_min_days=1,
        f_dd=2000, f_lock=100, q_days=5, q_amt=250, f_cons=0.50, buffer=2100, pay_frac=None, caps=[1500, 1500, 2000, 2500, 2500, 3000],
        cap_rule="above_buffer", pmin=500, split=1.0, max_pay=6, floor_after_pay=None),
    "LucidFlex": dict(
        e_fee=138.0, e_month=0.0, act=0.0, e_target=3000, e_dd=2000, e_cons=0.40, e_cons_of="profit", e_dll=None, e_min_days=1,
        f_dd=2000, f_lock=100, q_days=5, q_amt=150, f_cons=None, buffer=0, pay_frac=0.5, caps=[2000], cap_rule="frac_profit", pmin=500,
        split=0.9, max_pay=5, floor_after_pay=None),
}

W_GRID = [150, 200, 250, 300, 400, 500, 650, 800, 1000, 1250, 1500]
L_GRID = [150, 250, 400, 500, 650, 800, 1000, 1250, 1500, 2000]


def outcomes(h, l, c, W, L, mfe=False):
    """$ P&L per session for one long bracket (take W, stop L per contract); a bar touching both = stop. With mfe, also the best
    open profit before the exit (for intraday-trailing drawdowns)."""
    hitW = h >= W; hitL = l <= -L; T = c.shape[1]; big = T + 1
    tw = np.where(hitW.any(1), hitW.argmax(1), big); tl = np.where(hitL.any(1), hitL.argmax(1), big)
    stop = (tl < big) & (tl <= tw); take = (tw < big) & ~stop
    out = c[:, -1].astype(np.float64).copy(); out[stop] = -L; out[take] = W
    if not mfe:
        return out
    te = np.where(stop, tl, np.where(take, tw, T - 1))
    cm = np.maximum.accumulate(h, axis=1)
    m = np.minimum(cm[np.arange(len(c)), np.minimum(te, T - 1)].astype(np.float64), W)
    return out, np.maximum(m, 0.0)


def run(F: dict, pnl_e: np.ndarray, pnl_f: np.ndarray, starts: np.ndarray, mfe_e=None, mfe_f=None) -> np.ndarray:
    """Net $ (payouts x split - fees) per start over H sessions; one account slot, replaced when it fails or finishes."""
    A = len(starts)
    ph = np.full(A, 1 if F.get("e_skip") else 0); eq = np.zeros(A); pk = np.zeros(A); best = np.zeros(A); days = np.zeros(A, int); mdays = np.zeros(A, int)
    qd = np.zeros(A, int); cprof = np.zeros(A); cbest = np.zeros(A); npay = np.zeros(A, int); lastpay_eq = np.zeros(A); paid_once = np.zeros(A, bool)
    net = -np.full(A, F["e_fee"] + F["e_month"] + F.get("api_month", 0.0) * H / 20); caps = np.array(F["caps"], float)
    for d in range(H):
        i = starts + d
        ev = ph == 0
        x = np.where(ev, pnl_e[i], pnl_f[i])
        if F["e_dll"]:
            x = np.where(ev, np.maximum(x, -F["e_dll"]), x)
        if F.get("intraday") and mfe_e is not None:          # trailing from the intraday high: the peak sees the open profit
            io = ~ev if F["intraday"] == "funded" else np.ones(A, bool)     # "funded": EOD evaluation, intraday funded
            pk = np.where(io, np.maximum(pk, eq + np.where(ev, mfe_e[i], mfe_f[i])), pk)
        eq = eq + x; days += 1
        best = np.where(ev, np.maximum(best, x), best)
        # ---- evaluation
        floor_e = pk - F["e_dd"]
        fail_e = ev & (eq <= floor_e)
        pk = np.where(ev, np.maximum(pk, eq), pk)
        if F["e_cons"] is None:
            cons_ok = np.ones(A, bool)
        elif F["e_cons_of"] == "target":
            cons_ok = best <= F["e_cons"] * F["e_target"]
        else:
            cons_ok = best <= F["e_cons"] * np.maximum(eq, 1e-9)
        pass_e = ev & ~fail_e & (eq >= F["e_target"]) & cons_ok & (days >= F["e_min_days"])
        # monthly billing: one more month every 20 evaluation sessions
        mdays = np.where(ev, mdays + 1, mdays)
        bill = ev & ~pass_e & ~fail_e & (mdays % 20 == 0) & (F["e_month"] > 0)
        net = net - np.where(bill, F["e_month"], 0.0)
        # ---- funded
        fu = ph == 1
        fl_trail = np.minimum(pk - F["f_dd"], F["f_lock"])
        floor_f = np.where(paid_once & (F["floor_after_pay"] is not None), F["floor_after_pay"] if F["floor_after_pay"] is not None else 0, fl_trail)
        fail_f = fu & (eq <= floor_f)
        pk = np.where(fu, np.maximum(pk, eq), pk)
        qd = np.where(fu & (x >= F["q_amt"]) & (F["q_days"] > 0), qd + 1, qd)
        cprof = np.where(fu, cprof + x, cprof); cbest = np.where(fu, np.maximum(cbest, x), cbest)
        ok = fu & ~fail_f & (qd >= F["q_days"]) & (npay < F["max_pay"])
        ok &= np.where(paid_once, eq > lastpay_eq, True) if F["cap_rule"] != "v2" else ok
        if F["f_cons"] is not None:                           # a number, or a ladder by payout count
            fc = np.array(F["f_cons"], float)[np.minimum(npay, len(F["f_cons"]) - 1)] if isinstance(F["f_cons"], list) else F["f_cons"]
            ok &= (cprof > 0) & (cbest <= fc * cprof)
        if F.get("f_target"):                                  # profit needed since the last payout (a ladder by payout count)
            ok &= eq - lastpay_eq >= np.array(F["f_target"], float)[np.minimum(npay, len(F["f_target"]) - 1)]
        cap = caps[np.minimum(npay, len(caps) - 1)]
        if F["cap_rule"] == "frac_balance":
            amt = np.minimum(F["pay_frac"] * eq, cap)
        elif F["cap_rule"] == "frac_profit":
            amt = np.minimum(F["pay_frac"] * eq, cap)
        elif F["cap_rule"] == "above_buffer":
            amt = np.minimum(eq - F["buffer"], cap)
        else:                                                   # Tradeify V2: min($1,250, 2 x profit since last payout, above buffer)
            amt = np.minimum(np.minimum(cap, 2 * (eq - lastpay_eq)), eq - F["buffer"])
        pay = ok & (amt >= F["pmin"])
        net = net + np.where(pay, amt * F["split"], 0.0)
        eq = np.where(pay, eq - amt, eq); npay = np.where(pay, npay + 1, npay); lastpay_eq = np.where(pay, eq, lastpay_eq)
        paid_once |= pay; qd = np.where(pay, 0, qd); cprof = np.where(pay, 0.0, cprof); cbest = np.where(pay, 0.0, cbest)
        done = fu & (npay >= F["max_pay"])
        # ---- transitions
        to_f = pass_e
        net = net - np.where(to_f, F["act"], 0.0)
        new = (fail_e | fail_f | done) & (d < H - 1)
        net = net - np.where(new, F["e_fee"] + F["e_month"], 0.0)
        reset = new | to_f
        ph = np.where(to_f, 1, np.where(new, 1 if F.get("e_skip") else 0, ph))   # e_skip: direct funded, no evaluation
        for arr, v in ((eq, 0.0), (pk, 0.0), (best, 0.0), (cprof, 0.0), (cbest, 0.0), (lastpay_eq, 0.0)):
            arr[reset] = v
        days[reset] = 0; mdays[new] = 0; qd[reset] = 0; npay[reset] = 0; paid_once[reset] = False
    return net


def paths(era: str):
    (h, l, c), d = a23.market_paths("MNQ", era)
    return h.astype(np.float32), l.astype(np.float32), c.astype(np.float32)


def value(F, h, l, c, We, Le, Wf, Lf, starts) -> float:
    out = []
    for seed in SEEDS:
        rng = np.random.default_rng(seed); side = rng.random(len(c)) < 0.5
        def pnl(W, L):
            n = max(1, int(round(max(W, L) / 600.0)))       # contracts: keep each bracket within ~1 daily SD per contract
            lo = outcomes(h, l, c, W / n, L / n); sh = outcomes(-l, -h, -c, W / n, L / n)
            return n * np.where(side, lo, sh) - n * RT
        out.append(run(F, pnl(We, Le), pnl(Wf, Lf), starts).mean())
    return float(np.mean(out))


def main(argv=None) -> int:
    warnings.filterwarnings("ignore")
    E = {era: paths(era) for era in ("pre", "post")}
    res = {}
    for name, F in FIRMS.items():
        res[name] = {}
        for sel, oth in (("pre", "post"), ("post", "pre")):
            h, l, c = E[sel]; starts = np.arange(0, len(c) - H, 2)
            # stage 1: evaluation bracket with a neutral funded bracket; stage 2: funded bracket given the best evaluation one
            ge = {}
            for We, Le in itertools.product(W_GRID, L_GRID):
                if F["e_dll"] and Le > F["e_dll"]:
                    continue
                ge[(We, Le)] = value(F, h, l, c, We, Le, 300, 650, starts)
            be = max(ge, key=ge.get)
            gf = {(Wf, Lf): value(F, h, l, c, be[0], be[1], Wf, Lf, starts) for Wf, Lf in itertools.product(W_GRID, L_GRID)}
            bf = max(gf, key=gf.get)
            ge2 = {k: value(F, h, l, c, k[0], k[1], bf[0], bf[1], starts) for k in sorted(ge, key=ge.get, reverse=True)[:12]}
            be = max(ge2, key=ge2.get)
            h2, l2, c2 = E[oth]; starts2 = np.arange(0, len(c2) - H, 2)
            v_sel = value(F, h, l, c, be[0], be[1], bf[0], bf[1], starts); v_oth = value(F, h2, l2, c2, be[0], be[1], bf[0], bf[1], starts2)
            res[name][f"chosen_on_{sel}"] = {"eval": be, "funded": bf, f"value_{sel}": v_sel, f"value_{oth}": v_oth}
            print(f"{name:30} chosen on {sel}: eval take/stop {be}, funded {bf} | {sel} {v_sel:+8,.0f} | {oth} {v_oth:+8,.0f}", flush=True)
    (ROOT / "reports" / "a120_firm_strategies.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
