"""A61 - playing to Tradeify's live rules: payout gating, account mix, live play (decisions.md 626). No trial.

    python -m futuresres.reporting.a61_liveplay
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
from futuresres.reporting.a60_live import COOL, LIVE_DD, LIVE_LOCK, data, summary

ROOT = Path(__file__).resolve().parents[3]
MIXES = {"now": ("MNQ", "MGC", "MCL", "NKD", "FDXM"), "2NKD+2FDXM+MNQ": ("MNQ", "NKD", "NKD", "FDXM", "FDXM"), "3NKD+2FDXM": ("NKD", "NKD", "NKD", "FDXM", "FDXM")}


def simulate(common, P, window: int, accounts: tuple, gate=None, live_pre=(1_200, 1_000), live_post=(1_200, 1_000), cushion=2_000.0, live: bool = True) -> dict:
    s = a23.specs()["50K Daily"]; pe, ge, _, pf, gf, _ = a23.policy(s)
    S = len(common); starts = np.arange(0, S - window); A = len(starts)
    START, ddE, ddF = s.start, s.dd * 100.0, s.f_dd * 100.0
    ACC = [f"{m}#{i}" for i, m in enumerate(accounts)]; MK = {a: a.split('#')[0] for a in ACC}
    st = {m: {"phase": np.zeros(A, int), "eq": np.full(A, START), "pk": np.full(A, START), "best": np.zeros(A), "npay": np.zeros(A, int),
              "live": np.zeros(A, bool), "leq": np.zeros(A), "lpk": np.zeros(A), "lalive": np.zeros(A, bool)} for m in ACC}
    mode = np.zeros(A, int); cool = np.zeros(A, int); bookpay = np.zeros(A, int)
    NA = len(ACC); fees = np.full(A, NA * s.fee); paid_sim = np.zeros(A); paid_live = np.zeros(A); moves = np.zeros(A, int); first_live = np.full(A, -1)
    live_n_at_move = []; cool_days = np.zeros(A, int); closed_n = np.zeros(A, int)
    for d in range(window):
        idx = starts + d
        # cool-off: count down; at the end, five new evaluations
        cl = mode == 2
        cool_days += cl; cool = np.where(cl, cool - 1, cool)
        restart = cl & (cool <= 0)
        if restart.any():
            mode = np.where(restart, 0, mode); bookpay = np.where(restart, 0, bookpay)
            fees += np.where(restart & (d + 1 < window), NA * s.fee, 0.0)
            for m in ACC:
                a_ = st[m]
                for k, v in (("phase", 0), ("eq", START), ("pk", START), ("best", 0.0), ("npay", 0)):
                    a_[k] = np.where(restart, v, a_[k])
        sim = mode == 0; liv = mode == 1
        held = np.zeros(A, int)
        for m in ACC:
            held += (st[m]["phase"] == 1) & (st[m]["npay"] >= 1)
        open_gate = np.ones(A, bool) if gate is None else held >= gate
        for m in ACC:
            h, l, c, cost, has = P[MK[m]]; a_ = st[m]; act = has[idx]
            # ---- sim accounts (A23's step, restricted to starts in sim mode)
            ev = a_["phase"] == 0; fu = ~ev; eq, pk, best, npay = a_["eq"], a_["pk"], a_["best"], a_["npay"]
            b_e = np.clip(np.rint((eq - START) / 100).astype(int), ge["B_MIN"], ge["B_MAX"])
            pk_e = np.maximum(np.clip(np.rint((pk - START) / 100).astype(int), 0, ge["B_MAX"]), np.maximum(b_e, 0))
            bd_e = np.clip(np.rint(best / 100).astype(int), 0, ge["BD_MAX"])
            a_e = pe[b_e - ge["B_MIN"], pk_e, bd_e]
            b_f = np.clip(np.rint((eq - START) / 100).astype(int), gf["FMIN"], gf["FMAX"])
            pk_f = np.maximum(np.clip(np.rint((pk - START) / 100).astype(int), 0, gf["BUF"]), np.clip(b_f, 0, gf["BUF"]))
            a_f = pf[b_f - gf["FMIN"], pk_f, np.minimum(npay, s.live_after), np.zeros(A, int)]
            a = np.where(ev, a_e, a_f); W = (a // 100) * 100.0; L = (a % 100) * 100.0
            floor = np.where(ev, pk - ddE, np.where(pk >= START + ddF, START, pk - ddF))
            L = np.minimum(L, np.maximum(eq - floor - 1, 1))
            trade = sim & act & (a > 0) & (eq - floor > cost + 10)
            # ---- live accounts: fixed brackets, stop capped at the floor distance
            lfloor = np.where(a_["lpk"] >= LIVE_LOCK, 0.0, a_["lpk"] - LIVE_DD)
            lact = liv & a_["lalive"]
            locked = a_["lpk"] >= LIVE_LOCK
            Wl = np.where(locked, float(live_post[0]), float(live_pre[0])); Ll = np.minimum(np.where(locked, float(live_post[1]), float(live_pre[1])), np.maximum(a_["leq"] - lfloor - 1, 1))
            ltrade = lact & act & (a_["leq"] - lfloor > cost + 10)
            WW = np.where(trade, W + cost, np.where(ltrade, Wl + cost, 1e12)); LL = np.where(trade, np.maximum(L - cost, 1.0), np.where(ltrade, np.maximum(Ll - cost, 1.0), 1e12))
            pnl = a23._bracket(h[idx], l[idx], c[idx], WW, LL)
            pnl = np.round(np.where(trade | ltrade, pnl.astype(np.float64) - cost, 0.0), 2)
            # sim bookkeeping
            ne = eq + np.where(trade, pnl, 0.0); br = sim & act & ((ne <= floor) | ~trade)
            eq = np.where(sim, ne, eq); pk = np.where(sim, np.maximum(pk, ne), pk)
            best = np.where(sim & ev, np.maximum(best, pnl), best); prof = eq - START
            ok = sim & ev & ~br & (prof >= s.target * 100 - 0.005) & (best <= s.cons * prof + 0.005)
            amt = np.where(sim & fu & ~br, np.maximum(eq - (START + ddF), 0.0), 0.0)
            amt = np.where(npay >= s.live_after, amt, np.minimum(amt, s.cap_usd))
            amt = np.where((npay == 0) | open_gate, amt, 0.0)          # A61: hold later payouts until k accounts hold one
            got = amt > 0
            paid_sim += 0.9 * amt; eq -= amt; npay = npay + got; bookpay = bookpay + got
            reset = br | ok
            a_["phase"] = np.where(ok, 1, np.where(br, 0, a_["phase"]))
            a_["eq"] = np.where(reset, START, eq); a_["pk"] = np.where(reset, START, pk)
            a_["best"] = np.where(reset, 0.0, best); a_["npay"] = np.where(reset, 0, npay)
            fees += np.where(br & (d + 1 < window), s.fee, 0.0)
            # live bookkeeping
            leq = a_["leq"] + np.where(ltrade, pnl, 0.0); lpk = np.maximum(a_["lpk"], leq)
            lfloor2 = np.where(lpk >= LIVE_LOCK, 0.0, lpk - LIVE_DD)
            dead = lact & act & ((leq <= lfloor2) | ~ltrade)
            a_["lalive"] = a_["lalive"] & ~dead
            wd = np.where(a_["lalive"] & (lpk >= LIVE_LOCK) & (leq > cushion), leq - cushion, 0.0)
            paid_live += 0.8 * wd; leq -= wd
            a_["leq"], a_["lpk"] = leq, lpk
        # ---- move to live at the end of the day
        three = np.zeros(A, bool)
        for m in ACC:
            three |= (st[m]["phase"] == 1) & (st[m]["npay"] >= 3)
        trig = (mode == 0) & (three | (bookpay >= 10)) & live
        if trig.any():
            elig = {m: trig & (st[m]["phase"] == 1) & (st[m]["npay"] >= 1) for m in ACC}
            anyone = np.zeros(A, bool)
            for m in ACC:
                anyone |= elig[m]
            go = trig & anyone
            for m in ACC:
                e = elig[m] & go
                st[m]["lalive"] = np.where(go, e, st[m]["lalive"]); st[m]["leq"] = np.where(go, 0.0, st[m]["leq"]); st[m]["lpk"] = np.where(go, 0.0, st[m]["lpk"])
                closed_n += go & ~e
            live_n_at_move += [int(sum(elig[m][i] for m in ACC)) for i in np.where(go)[0]]
            mode = np.where(go, 1, mode); moves += go; first_live = np.where(go & (first_live < 0), d + 1, first_live)
        # ---- all live accounts failed: cool-off
        alive = np.zeros(A, bool)
        for m in ACC:
            alive |= st[m]["lalive"]
        endl = (mode == 1) & ~alive
        mode = np.where(endl, 2, mode); cool = np.where(endl, COOL, cool)
    net = paid_sim + paid_live - fees
    live_eq_end = np.zeros(A)
    for m in ACC:
        live_eq_end += np.where(st[m]["lalive"], st[m]["leq"], 0.0)     # A62: equity still in live accounts at the end (not cash)
    return {"start": starts, "net": net, "live_eq_end": live_eq_end, "paid_sim": paid_sim, "paid_live": paid_live, "fees": fees, "moves": moves, "first_live": first_live,
            "cool_days": cool_days, "closed": closed_n, "live_at_move": np.array(live_n_at_move), "evals": fees / s.fee}



def run(cp, Pp, cq, Pq, window, **kw):
    r = simulate(cp, Pp, window, **kw); st = np.array(cp[: len(cp) - window]); m24 = np.array([x < dt.date(2025, 1, 1) for x in st])
    rq = simulate(cq, Pq, window, **kw)
    return {"2021-24": float(r["net"][m24].mean()), "2025 starts": summary(r, ~m24), "2021-26": summary(r, np.ones(len(st), bool)),
            "2010-20": summary(rq, np.ones(len(rq["net"]), bool)), "live_at_move": {str(k): float(np.mean(r["live_at_move"] == k)) for k in range(1, 6)} if len(r["live_at_move"]) else {}}


def show(lab, x):
    a, b, c = x["2025 starts"], x["2021-26"], x["2010-20"]
    print(f"{lab:34}: 2021-24 {x['2021-24']:+7,.0f} | 2025 starts {a['net_mean']:+7,.0f} ({a['p_pos']:.0%}) | 2021-26 {b['net_mean']:+7,.0f} ({b['p_pos']:.0%}, p10 {b['p10']:+,.0f}) "
          f"| 2010-20 {c['net_mean']:+7,.0f} ({c['p_pos']:.0%}) | live at move {x['live_at_move']}", flush=True)


def main() -> int:
    warnings.filterwarnings("ignore"); out = {}
    cp, Pp = data("post"); cq, Pq = data("pre")
    print("Stage 1 - payout gating (mix now)", flush=True)
    s1 = {}
    for k in (None, 2, 3, 4, 5):
        s1[k] = run(cp, Pp, cq, Pq, 84, accounts=MIXES["now"], gate=k); show(f"gate {k}", s1[k])
    k_best = max(s1, key=lambda k: s1[k]["2021-24"]); out["stage1"] = {str(k): v for k, v in s1.items()}
    print(f"Stage 2 - account mix (gate {k_best})", flush=True)
    s2 = {}
    for nm, mix in MIXES.items():
        s2[nm] = s1[k_best] if nm == "now" else run(cp, Pp, cq, Pq, 84, accounts=mix, gate=k_best); show(f"mix {nm}", s2[nm])
    mix_best = max(s2, key=lambda k: s2[k]["2021-24"]); out["stage2"] = s2
    print(f"Stage 3 - live play before the lock (gate {k_best}, mix {mix_best})", flush=True)
    s3 = {}
    for pre in ((500, 500), (800, 800), (1_200, 1_000)):
        s3[pre] = s2[mix_best] if pre == (1_200, 1_000) else run(cp, Pp, cq, Pq, 84, accounts=MIXES[mix_best], gate=k_best, live_pre=pre); show(f"pre-lock {pre}", s3[pre])
    pre_best = max(s3, key=lambda k: s3[k]["2021-24"]); out["stage3"] = {str(k): v for k, v in s3.items()}
    out["chosen"] = {"gate": k_best, "mix": mix_best, "live_pre": list(pre_best)}
    print(f"Chosen: gate {k_best}, mix {mix_best}, pre-lock {pre_best}. One year (252 sessions):", flush=True)
    for lab, kw in (("baseline (A60)", dict(accounts=MIXES["now"])), ("chosen", dict(accounts=MIXES[mix_best], gate=k_best, live_pre=pre_best))):
        x = run(cp, Pp, cq, Pq, 252, **kw); out[f"252 {lab}"] = x; show(f"252 {lab}", x)
    (ROOT / "reports" / "a61_liveplay.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
