"""A63 - other prop firms' 50K rules against Tradeify, in one joint simulation (decisions.md 630). No trial.

Generalises A61's book simulation: per-firm evaluation fee, evaluation consistency and minimum days, funded drawdown type (end-of-day
or intraday trailing, from each day's path maximum before the exit), payout rule, profit split, account limit, and live rule (Tradeify's
trigger, a payout-count trigger, or none), cooldown. The bracket policy is A23's solved 50K Daily policy for every firm (same $3,000
target / $2,000 drawdown game; an approximation for firms whose payout rules differ).

    python -m futuresres.reporting.a63_firms
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
from futuresres.reporting.a60_live import data, summary

ROOT = Path(__file__).resolve().parents[3]
START = 50_000.0

#: firm -> rules. payout: (kind, buffer above start, minimum, cap); live: (kind, n) with kind tradeify | after | never
FIRMS = {
    "Tradeify Select Daily": dict(fee=80.0, cons=0.40, min_days=1, fdd="eod", lock=START, payout=("cap", 2_000.0, 0.0, 1_250.0), split=0.9,
                                  max_acc=5, live=("tradeify", 10), live_split=0.8, cool=20, live_room_bonus=False),
    "MFF Rapid EOD": dict(fee=157.0, cons=0.30, min_days=4, fdd="eod", lock=START + 100, payout=("above", 2_100.0, 500.0, None), split=0.9,
                          max_acc=3, live=("never", 0), live_split=0.9, cool=20, live_room_bonus=False),
    "TPT PRO": dict(fee=150.0, cons=0.50, min_days=3, fdd="intraday", lock=START, payout=("above", 2_000.0, 0.01, None), split=0.8,
                    max_acc=5, live=("never", 0), live_split=0.9, cool=20, live_room_bonus=False),
    "Lucid Daily": dict(fee=150.0, cons=0.50, min_days=1, fdd="intraday", lock=START + 100, payout=("above", 2_100.0, 500.0, None), split=0.9,
                        max_acc=5, live=("never", 0), live_split=0.9, cool=10, live_room_bonus=True),
}
LIVE_DD, LIVE_LOCK = 2_000.0, 2_000.0


def bracket_mfe(h, l, c, W, L):
    """(net-of-nothing P&L, maximum favourable excursion before the exit) per row; a bar touching both = stop."""
    A, T = c.shape
    hitW = h >= W[:, None]; hitL = l <= -L[:, None]; big = T + 1
    tw = np.where(hitW.any(1), hitW.argmax(1), big); tl = np.where(hitL.any(1), hitL.argmax(1), big)
    stop = (tl < big) & (tl <= tw); take = (tw < big) & ~stop
    out = c[:, -1].astype(np.float64).copy(); out[stop] = -L[stop]; out[take] = W[take]
    te = np.where(stop, tl, np.where(take, tw, T - 1))
    cm = np.maximum.accumulate(h, axis=1); mfe = cm[np.arange(A), np.minimum(te, T - 1)].astype(np.float64)
    mfe = np.where(take, W, np.minimum(mfe, np.where(stop, np.inf, np.inf)))
    return out, np.maximum(mfe, 0.0)


def simulate(common, P, window: int, accounts: tuple, F: dict, live_override=None) -> dict:
    s = F.get("spec") or a23.specs()["50K Daily"]; pe, ge, _, pf, gf, _ = a23.policy(s)
    S = len(common); starts = np.arange(0, S - window); A = len(starts); ddE = ddF = F.get("dd", 2_000.0); TGT = F.get("target", 3_000.0)
    live_kind, live_n = live_override or F["live"]
    ACC = [f"{m}#{i}" for i, m in enumerate(accounts[: F["max_acc"]])]; MK = {a: a.split("#")[0] for a in ACC}; NA = len(ACC)
    st = {m: {"phase": np.zeros(A, int), "eq": np.full(A, START), "pk": np.full(A, START), "best": np.zeros(A), "days": np.zeros(A, int),
              "npay": np.zeros(A, int), "lpay": np.full(A, START), "cyc": np.zeros(A, int), "cprof": np.zeros(A), "cbest": np.zeros(A), "leq": np.zeros(A), "lpk": np.zeros(A), "lroom": np.full(A, F.get("live_dd", LIVE_DD)), "lalive": np.zeros(A, bool)} for m in ACC}
    mode = np.zeros(A, int); cool = np.zeros(A, int); bookpay = np.zeros(A, int)
    if F.get("no_eval"):                                               # A85: Lightning - funded from the start, no evaluation
        for m in ACC:
            st[m]["phase"] = np.ones(A, int)
    for i, ini in enumerate(F.get("init") or []):                      # A69: an account's starting state (the switch-over)
        if ini:
            for k_, v_ in ini.items():
                st[ACC[i]][k_] = np.full(A, v_, dtype=st[ACC[i]][k_].dtype)
    bookpay = bookpay + int(F.get("init_bookpay", 0))
    fees = np.full(A, NA * F["fee"]) - F["fee"] * sum(1 for x in (F.get("init") or []) if x); paid_sim = np.zeros(A); paid_live = np.zeros(A); moves = np.zeros(A, int); cool_days = np.zeros(A, int)
    kind, buf, pmin, cap = F["payout"]
    min_cash = np.full(A, -NA * F["fee"]); first_pay = np.full(A, -1)        # A67: the trader's cash path
    pay2_day = np.full(A, -1); fees_pay2 = np.zeros(A); low_pay2 = np.zeros(A)   # A68: when the book's 2nd payout lands
    for d in range(window):
        idx = starts + d
        cl = mode == 2; cool_days += cl; cool = np.where(cl, cool - 1, cool); restart = cl & (cool <= 0)
        if restart.any():
            mode = np.where(restart, 0, mode); bookpay = np.where(restart, 0, bookpay)
            fees += np.where(restart & (d + 1 < window), NA * F["fee"], 0.0)
            for m in ACC:
                for k, v in (("phase", 1 if F.get("no_eval") else 0), ("eq", START), ("pk", START), ("best", 0.0), ("npay", 0), ("days", 0),
                             ("cyc", 0), ("cprof", 0.0), ("cbest", 0.0)):
                    st[m][k] = np.where(restart, v, st[m][k])
        sim = mode == 0; liv = mode == 1
        hold_k = F.get("hold_first_until")
        if hold_k is not None:                                          # A69: hold account 0's payouts until k others hold one
            others = np.zeros(A, int)
            for m in ACC[1:]:
                others += (st[m]["phase"] == 1) & (st[m]["npay"] >= 1)
            release0 = others >= hold_k
        for m in ACC:
            h, l, c, cost, has = P[MK[m]]; a_ = st[m]; act = has[idx]
            if F.get("live_paths"):                           # A76: live accounts trade their own (longer) window; same width as P's
                hL, lL, cL, hasL = F["live_paths"][MK[m]]; act_l = hasL[idx]
            else:
                act_l = act
            if F.get("pol"):                                  # A71: per-market policies (eval, funded) from the real-game solve
                pe, ge, pf, gf = F["pol"][MK[m]]
            ev = a_["phase"] == 0; fu = ~ev; eq, pk, best, npay = a_["eq"], a_["pk"], a_["best"], a_["npay"]
            b_e = np.clip(np.rint((eq - START) / 100).astype(int), ge["B_MIN"], ge["B_MAX"])
            pk_e = np.maximum(np.clip(np.rint((pk - START) / 100).astype(int), 0, ge["B_MAX"]), np.maximum(b_e, 0))
            bd_e = np.clip(np.rint(best / 100).astype(int), 0, ge["BD_MAX"])
            a_e = pe[b_e - ge["B_MIN"], pk_e, bd_e]
            b_f = np.clip(np.rint((eq - START) / 100).astype(int), gf["FMIN"], gf["FMAX"])
            pk_f = np.maximum(np.clip(np.rint((pk - START) / 100).astype(int), 0, gf["BUF"]), np.clip(b_f, 0, gf["BUF"]))
            a_f = pf[b_f - gf["FMIN"], pk_f, np.minimum(npay, s.live_after), np.zeros(A, int)]
            a = np.where(ev, a_e, a_f); W = (a // 100) * 100.0; L = (a % 100) * 100.0
            if F.get("kind_goal"):                            # A85: Lightning - a day may not exceed its consistency share of the goal
                g_ = np.where(npay == 0, F["goals"][0], F["goals"][1]); c_ = np.array(F["cons_goal"])[np.minimum(npay, len(F["cons_goal"]) - 1)]
                W = np.where(fu, np.minimum(W, np.maximum(c_ * g_ - 100.0, 100.0)), W)
            if F.get("fscale"):                               # A65: funded-stage bracket scaling (take, stop factors)
                W = np.where(fu, W * F["fscale"][0], W); L = np.where(fu, L * F["fscale"][1], L)
            # A75: evaluation / funded accounts may trade sm x the plan's contracts; "price" keeps the price distances ($ x sm, the stop
            # still within the $1,000 daily loss limit)
            scope = {"eval": ev, "funded": fu}.get(F.get("sim_k_where"), np.ones(A, bool))
            sm = np.where(scope, (F.get("sim_k") or {}).get(MK[m], 1.0), 1.0)
            if F.get("sim_k_price"):
                W = W * sm; L = np.minimum(L * sm, F.get("daily_limit", 1_000.0))
            scost = cost * sm
            floor = np.where(ev, pk - ddE, np.where(pk >= F["lock"] + ddF, F["lock"], pk - ddF))
            L = np.minimum(L, np.maximum(eq - floor - 1, 1))
            idle = (m == ACC[0]) & bool(F.get("idle_first"))            # A70: account 0 sits out the simulated stage (no trades, no breach)
            trade = sim & act & (a > 0) & (eq - floor > scost + 10) & (not idle)
            LLK = F.get("live_dd", LIVE_LOCK)
            lfloor = np.where(a_["lpk"] >= LLK, 0.0, a_["lpk"] - a_["lroom"])
            lact = liv & a_["lalive"]; locked = a_["lpk"] >= LLK
            if F.get("live_pol"):                             # A71: the solved live-account policy
                la_, lg_ = F["live_pol"][MK[m]]
                lb = np.clip(np.rint(a_["leq"] / 100).astype(int), lg_["LMIN"], lg_["LMAX"])
                lp = np.maximum(np.clip(np.rint(a_["lpk"] / 100).astype(int), 0, lg_["LOCK"]), np.clip(lb, 0, lg_["LOCK"]))
                la = la_[lb - lg_["LMIN"], lp]; Wl = (la // 100) * 100.0; Ll = (la % 100) * 100.0
            else:
                Wl = np.full(A, 1_200.0 * F.get("k", 1.0)); Ll = np.full(A, 1_000.0 * F.get("k", 1.0))
            # A74: live accounts may trade lm x the plan's contracts (from the live start, or once locked); "price" keeps the price distances
            lm = np.where(lact & (locked if F.get("live_k_when") == "locked" else True), (F.get("live_k") or {}).get(MK[m], 1.0), 1.0)
            if F.get("live_k_price"):
                Wl = Wl * lm; Ll = Ll * lm
            lcost = cost * lm
            Ll = np.minimum(Ll, np.maximum(a_["leq"] - lfloor - 1, 1))
            ltrade = lact & act_l & (a_["leq"] - lfloor > lcost + 10)
            WW = np.where(trade, (W + scost) / sm, np.where(ltrade, (Wl + lcost) / lm, 1e12))
            LL = np.where(trade, np.maximum(L - scost, 1.0) / sm, np.where(ltrade, np.maximum(Ll - lcost, 1.0) / lm, 1e12))
            if F.get("live_paths"):
                lt = ltrade[:, None]
                raw, mfe = bracket_mfe(np.where(lt, hL[idx], h[idx]), np.where(lt, lL[idx], l[idx]), np.where(lt, cL[idx], c[idx]), WW, LL)
            else:
                raw, mfe = bracket_mfe(h[idx], l[idx], c[idx], WW, LL)
            raw = np.where(ltrade, raw * lm, np.where(trade, raw * sm, raw)); mfe = np.where(trade, mfe * sm, mfe)
            pnl = np.round(np.where(trade, raw - scost, np.where(ltrade, raw - lcost, 0.0)), 2)
            # ---- sim accounts
            ne = eq + np.where(trade, pnl, 0.0)
            if F["fdd"] == "intraday":                    # funded floor trails the intraday high (the day's best point before the exit)
                ipk = np.where(fu & trade, np.maximum(pk, eq + mfe - cost), pk)
                ifloor = np.where(ipk >= F["lock"] + ddF, F["lock"], ipk - ddF)
                floor_chk = np.where(fu, np.maximum(floor, ifloor), floor)
            else:
                ipk = pk; floor_chk = floor
            br = sim & act & ((ne <= floor_chk) | ~trade) & (not idle)
            eq = np.where(sim, ne, eq); pk = np.where(sim, np.maximum(np.maximum(pk, ne), np.where(fu, ipk, pk)), pk)
            best = np.where(sim & ev, np.maximum(best, pnl), best); a_["days"] = a_["days"] + (sim & act & ev & trade)
            prof = eq - START
            ok = sim & ev & ~br & (prof >= TGT - 0.005) & (best <= F["cons"] * prof + 0.005) & (a_["days"] >= F["min_days"])
            if kind == "cap":
                amt = np.where(sim & fu & ~br, np.maximum(eq - (START + buf), 0.0), 0.0); amt = np.minimum(amt, cap)
            elif kind == "daily":                         # Tradeify Select Daily, official help article (decisions.md 805): above the
                since = eq - a_["lpay"]                   # buffer, <= cap, <= 2x the profit since the last payout (> 0), >= the minimum
                amt = np.where(sim & fu & ~br & (since > 0), np.minimum(np.minimum(np.maximum(eq - (START + buf), 0.0), cap), 2.0 * since), 0.0)
                amt = np.where(amt >= pmin, amt, 0.0)
            elif kind == "cycle":                         # Phidias: a request every N funded days, capped, best day <= cons_f x cycle profit
                a_["cyc"] = np.where(sim & fu & act, a_["cyc"] + 1, a_["cyc"])
                a_["cprof"] = np.where(sim & fu, a_["cprof"] + np.where(trade, pnl, 0.0), a_["cprof"])
                a_["cbest"] = np.where(sim & fu, np.maximum(a_["cbest"], np.where(trade, pnl, 0.0)), a_["cbest"])
                okc = (a_["cyc"] >= F["cycle_days"]) & (a_["cprof"] > 0) & (a_["cbest"] <= F["cons_f"] * a_["cprof"] + 0.005)
                amt = np.where(sim & fu & ~br & okc, np.maximum(eq - (START + buf), 0.0), 0.0); amt = np.minimum(amt, cap)
                amt = np.where(amt >= pmin, amt, 0.0)
            elif kind in ("growth", "goal"):              # A85: Tradeify Growth / Lightning funded payouts
                a_["cprof"] = np.where(sim & fu, a_["cprof"] + np.where(trade, pnl, 0.0), a_["cprof"])
                a_["cbest"] = np.where(sim & fu, np.maximum(a_["cbest"], np.where(trade, pnl, 0.0)), a_["cbest"])
                capn = np.array(F["caps"])[np.minimum(npay, len(F["caps"]) - 1)]
                if kind == "growth":                      # >= 5 days of >= $150, balance >= start + $3,000, largest day <= 35% of the cycle
                    a_["cyc"] = np.where(sim & fu & trade & (pnl >= F["win_day"]), a_["cyc"] + 1, a_["cyc"])
                    okp = (a_["cyc"] >= 5) & (eq >= START + F["min_bal"]) & (a_["cbest"] <= F["cons_f"] * a_["cprof"] + 0.005)
                    amt = np.where(sim & fu & ~br & okp, np.minimum(np.maximum(eq - (START + buf), 0.0) * F.get("pay_frac", 1.0), capn), 0.0)
                else:                                     # goal $3,000 then $2,000; largest day <= cons x max(goal, cycle profit)
                    g_ = np.where(npay == 0, F["goals"][0], F["goals"][1]); c_ = np.array(F["cons_goal"])[np.minimum(npay, len(F["cons_goal"]) - 1)]
                    okp = (a_["cprof"] >= g_) & (a_["cbest"] <= c_ * np.maximum(g_, a_["cprof"]) + 0.005)
                    amt = np.where(sim & fu & ~br & okp, np.minimum(np.minimum(a_["cprof"], np.maximum(eq - START, 0.0)), capn), 0.0)
                amt = np.where(amt >= pmin, amt, 0.0)
            else:
                amt = np.where(sim & fu & ~br, np.maximum(eq - (START + buf), 0.0), 0.0); amt = np.where(amt >= pmin, amt, 0.0)
            if hold_k is not None and m == ACC[0]:
                amt = np.where(release0, amt, 0.0)
            got = amt > 0
            spl = F["split"] if not isinstance(F["split"], tuple) else np.array(F["split"])[np.minimum(npay, len(F["split"]) - 1)]
            paid_sim += spl * amt; eq -= amt; npay = npay + got; bookpay = bookpay + got
            a_["lpay"] = np.where(got, eq, a_["lpay"])
            if kind in ("cycle", "growth", "goal"):
                a_["cyc"] = np.where(got, 0, a_["cyc"]); a_["cprof"] = np.where(got, 0.0, a_["cprof"]); a_["cbest"] = np.where(got, 0.0, a_["cbest"])
            reset = br | ok
            a_["phase"] = np.where(ok, 1, np.where(br, 1 if F.get("no_eval") else 0, a_["phase"]))
            a_["eq"] = np.where(reset, START, eq); a_["pk"] = np.where(reset, START, pk)
            a_["best"] = np.where(reset, 0.0, best); a_["npay"] = np.where(reset, 0, npay); a_["days"] = np.where(reset, 0, a_["days"])
            a_["lpay"] = np.where(reset, START, a_["lpay"])
            for k in ("cyc", "cprof", "cbest"):
                a_[k] = np.where(reset, 0, a_[k])
            fees += np.where(br & (d + 1 < window), F["fee"], 0.0)
            # ---- live accounts
            leq = a_["leq"] + np.where(ltrade, pnl, 0.0); lpk = np.maximum(a_["lpk"], leq)
            lfloor2 = np.where(lpk >= LLK, 0.0, lpk - a_["lroom"])
            dead = lact & act_l & ((leq <= lfloor2) | ~ltrade)
            a_["lalive"] = a_["lalive"] & ~dead
            CU = F.get("live_cushion", 2_000.0)                # A73: withdraw above this once locked (100K: its $3,000 lock)
            wd = np.where(a_["lalive"] & (lpk >= LLK) & (leq > CU), leq - CU, 0.0)
            paid_live += F["live_split"] * wd; leq -= wd
            a_["leq"], a_["lpk"] = leq, lpk
        # ---- move to live
        if live_kind != "never":
            three = np.zeros(A, bool)
            for m in ACC:
                three |= (st[m]["phase"] == 1) & (st[m]["npay"] >= 3)
            trig = (mode == 0) & ((bookpay >= live_n) | (three if live_kind == "tradeify" else False))
            if trig.any():
                elig = {m: trig & (st[m]["phase"] == 1) & (st[m]["npay"] >= 1) for m in ACC}
                anyone = np.zeros(A, bool)
                for m in ACC:
                    anyone |= elig[m]
                go = trig & anyone
                for m in ACC:
                    e = elig[m] & go
                    room = F.get("live_dd", LIVE_DD) + (np.maximum(st[m]["eq"] - START, 0.0) if F["live_room_bonus"] else 0.0)
                    st[m]["lalive"] = np.where(go, e, st[m]["lalive"]); st[m]["leq"] = np.where(go, 0.0, st[m]["leq"])
                    st[m]["lpk"] = np.where(go, 0.0, st[m]["lpk"]); st[m]["lroom"] = np.where(go, room, st[m]["lroom"])
                mode = np.where(go, 1, mode); moves += go
            alive = np.zeros(A, bool)
            for m in ACC:
                alive |= st[m]["lalive"]
            endl = (mode == 1) & ~alive
            mode = np.where(endl, 2, mode); cool = np.where(endl, F["cool"], cool)
        cash = paid_sim + paid_live - fees - F.get("data_month", 0.0) * (d + 1) / 21.0
        min_cash = np.minimum(min_cash, cash); first_pay = np.where((first_pay < 0) & (paid_sim + paid_live > 0), d + 1, first_pay)
        hit2 = (pay2_day < 0) & (bookpay >= 2)
        pay2_day = np.where(hit2, d + 1, pay2_day); fees_pay2 = np.where(hit2, fees, fees_pay2); low_pay2 = np.where(hit2, min_cash, low_pay2)
    net = paid_sim + paid_live - fees
    return {"start": starts, "net": net, "min_cash": min_cash, "first_pay": first_pay, "pay2_day": pay2_day, "fees_pay2": fees_pay2, "low_pay2": low_pay2, "paid_sim": paid_sim, "paid_live": paid_live, "fees": fees, "moves": moves, "first_live": np.full(A, -1),
            "cool_days": cool_days, "closed": np.zeros(A, int), "live_at_move": np.array([]), "evals": fees / F["fee"]}


PHIDIAS_SPEC = a23.Spec("Phidias 50K", 50_000, 150.0, 40, 25, 1.0, 26, 20, None, cap_usd=2000.0)
FIRMS["Phidias Fundamental"] = dict(fee=150.0, cons=1.0, min_days=3, fdd="eod", lock=START + 100, payout=("cycle", 2_600.0, 500.0, 2_000.0),
                                    cycle_days=10, cons_f=0.30, split=0.8, max_acc=15, live=("never", 0), live_split=0.9, cool=20,
                                    live_room_bonus=False, dd=2_500.0, target=4_000.0, spec=PHIDIAS_SPEC)
FIRMS["Phidias Premium"] = dict(FIRMS["Phidias Fundamental"], min_days=1, cycle_days=5, split=(0.75, 0.80, 0.85, 0.90, 1.0))

MIXES = {"5: 3NKD+2FDXM": ("NKD", "NKD", "NKD", "FDXM", "FDXM"), "5: NKD×5": ("NKD",) * 5, "5: now": ("MNQ", "MGC", "MCL", "NKD", "FDXM"),
         "5: no Eurex (NKD×3, MNQ, MGC)": ("NKD", "NKD", "NKD", "MNQ", "MGC"), "3: NKD×3": ("NKD",) * 3, "3: NKD, MNQ, MGC": ("NKD", "MNQ", "MGC"),
         "15: 9NKD+6FDXM": ("NKD",) * 9 + ("FDXM",) * 6, "5: 4NKD+1FDXM": ("NKD",) * 4 + ("FDXM",), "5: 2NKD+3FDXM": ("NKD",) * 2 + ("FDXM",) * 3}
RUNS = [("Tradeify Select Daily", "5: 3NKD+2FDXM", None), ("Tradeify Select Daily", "5: now", None), ("Tradeify Select Daily", "5: no Eurex (NKD×3, MNQ, MGC)", None),
        ("MFF Rapid EOD", "3: NKD×3", None), ("MFF Rapid EOD", "3: NKD×3", ("after", 10)), ("MFF Rapid EOD", "3: NKD, MNQ, MGC", None),
        ("TPT PRO", "5: no Eurex (NKD×3, MNQ, MGC)", None), ("TPT PRO", "5: NKD×5", None), ("TPT PRO", "5: no Eurex (NKD×3, MNQ, MGC)", ("after", 10)),
        ("Lucid Daily", "5: no Eurex (NKD×3, MNQ, MGC)", None), ("Lucid Daily", "5: no Eurex (NKD×3, MNQ, MGC)", ("after", 10)),
        ("Lucid Daily", "5: no Eurex (NKD×3, MNQ, MGC)", ("after", 20))]


def main() -> int:
    warnings.filterwarnings("ignore"); out = {}
    cp, Pp = data("post"); cq, Pq = data("pre")
    st = np.array(cp[: len(cp) - 84]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st])
    for firm, mix, lo in RUNS:
        F = FIRMS[firm]; r = simulate(cp, Pp, 84, MIXES[mix], F, lo); rq = simulate(cq, Pq, 84, MIXES[mix], F, lo)
        key = f"{firm} | {mix} | live {lo or F['live']}"
        out[key] = {"2025 starts": summary(r, m25), "2021-26": summary(r, np.ones(len(st), bool)), "2010-20": summary(rq, np.ones(len(rq["net"]), bool))}
        a, b, c = out[key]["2025 starts"], out[key]["2021-26"], out[key]["2010-20"]
        print(f"{key:78}: 2025 {a['net_mean']:+8,.0f} ({a['p_pos']:.0%}) | 2021-26 {b['net_mean']:+8,.0f} ({b['p_pos']:.0%}, p10 {b['p10']:+,.0f}) | 2010-20 "
              f"{c['net_mean']:+8,.0f} ({c['p_pos']:.0%}) | fees {b['fees']:,.0f} sim paid {b['paid_sim']:,.0f} live paid {b['paid_live']:,.0f}", flush=True)
    (ROOT / "reports" / "a63_firms.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
