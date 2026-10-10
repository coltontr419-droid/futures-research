"""A13 - contract size as part of the solved policy: the staking game re-solved over (take, stop, contracts), with
each action's NET outcome distribution measured on real sessions (stops at the stop price), learned on one
history and tested on the other in BOTH directions, against the fair-odds A01 policy at the fixed demo size.
A COMPUTATION; zero edge (drift removed); no trial. decisions.md 113.

    python -m futuresres.reporting.a13_size_policy --product MNQ --train pre    (one run per process)
    python -m futuresres.reporting.a13_size_policy --log                        (merge the four runs, record)

A05 (decisions.md 102) learned odds on 2015-20 at a fixed 2 MNQ and failed on 2021-26 (43% vs 61%): fitted to
one regime, and its reduced menu had no small end-game brackets. Here: sizes MNQ 2-6, MGC 4-12; brackets
W in {1,2,3,4,6,8,10,12,15,20,30} x L in {2,4,5,6,8,10} ($100 units, A01's grid less the rarely-used). Decided
in advance: the size-aware policy is adopted only if it beats the fixed-size fair-odds policy on mean net AND
P(payout) in BOTH train/test directions, for that product.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a01_game as g
import futuresres.reporting.a02_real as a2
import futuresres.reporting.a08_gold as a8

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a13_size_policy.json"
PLANS = {"MNQ": {"window": "rth_0930_1600", "rt": 2.32, "sizes": (2, 3, 4, 5, 6), "fixed": 4},
         "MGC": {"window": "london_0300_1130", "rt": 3.32, "sizes": (4, 6, 8, 10, 12), "fixed": 8}}
W_SET = (1, 2, 3, 4, 6, 8, 10, 12, 15, 20, 30)
L_SET = (2, 4, 5, 6, 8, 10)
MIN_P = 1e-3
START, HORIZON, FEE = 50_000.0, 84, 80.0


def _code(n: int, W: int, L: int) -> int:
    return n * 10000 + W * 100 + L


def _decode(code):
    return code // 10000, (code // 100) % 100, code % 100


def outcome_table(h, l, c, prod: str) -> dict:
    """{code: [(delta in $100, p)]}: NET outcome of each (n, W, L) bracket over these sessions, stops at the stop."""
    p = PLANS[prod]
    a2.STOP_FILL = "level"
    S = len(c); table = {}
    for n in p["sizes"]:
        cost = p["rt"] * n
        hn, ln, cn = h * n, l * n, c * n                     # GROSS $ paths for n contracts
        for W in W_SET:
            for L in L_SET:
                Wd = np.full(S, W * 100.0 + cost); Ld = np.full(S, max(L * 100.0 - cost, 1.0))
                pnl, _, _ = a2._bracket_day(hn, ln, cn, Wd, Ld)
                units = np.clip(np.rint((pnl - cost) / 100).astype(int), -2 * g.DAILY, g.B_MAX)
                v, k = np.unique(units, return_counts=True)
                pr = k / S; keep = pr >= MIN_P; pr = pr[keep] / pr[keep].sum()
                table[_code(n, W, L)] = list(zip(v[keep].tolist(), pr.tolist()))
    return table


def solve_eval(table, days: int = 21) -> np.ndarray:
    """a05_empirical.solve_eval, over coded actions."""
    nb = g.B_MAX - g.B_MIN + 1
    shape = (nb, g.B_MAX + 1, g.BD_MAX + 1)
    B = np.broadcast_to((np.arange(nb)[:, None, None] + g.B_MIN), shape)
    PK = np.broadcast_to(np.arange(g.B_MAX + 1)[None, :, None], shape)
    BD = np.broadcast_to(np.arange(g.BD_MAX + 1)[None, None, :], shape)
    valid = (PK >= np.maximum(B, 0)) & (B > PK - g.DD)
    V = np.zeros(shape); act = np.zeros(shape, int)
    for _ in range(days):
        best = np.full(shape, -1.0); act = np.zeros(shape, int)
        for code, outs in table.items():
            val = np.zeros(shape)
            for dlt, pr in outs:
                nb_ = B + dlt
                fail = nb_ <= PK - g.DD
                nb_c = np.clip(nb_, g.B_MIN, g.B_MAX)
                npk = np.minimum(np.maximum(PK, nb_c), g.B_MAX)
                nbd = np.minimum(np.maximum(BD, max(dlt, 0)), g.BD_MAX)
                passed = (nb_c >= g.TARGET) & (np.maximum(BD, max(dlt, 0)) <= g.CONS * nb_c)
                val += pr * np.where(fail, 0.0, np.where(passed, 1.0, V[nb_c - g.B_MIN, npk, nbd]))
            val = np.where(valid, val, -1.0)
            better = val > best + 1e-12
            best = np.where(better, val, best); act = np.where(better, code, act)
        V = np.where(valid, np.maximum(best, 0.0), 0.0)
    return act


def solve_funded(table, days: int = 21) -> np.ndarray:
    """a05_empirical.solve_funded, over coded actions."""
    nb = g.F_BMAX - g.F_BMIN + 1
    shape = (nb, g.BUFFER + 1, g.LIVE_AFTER + 1)
    B = np.broadcast_to((np.arange(nb)[:, None, None] + g.F_BMIN), shape)
    PK = np.broadcast_to(np.arange(g.BUFFER + 1)[None, :, None], shape)
    N = np.broadcast_to(np.arange(g.LIVE_AFTER + 1)[None, None, :], shape)
    floor = np.where(PK >= g.BUFFER, 0, PK - g.DD)
    valid = (B > floor) & (PK >= np.minimum(np.maximum(B, 0), g.BUFFER))
    V = np.zeros(shape); act = np.zeros(shape, int)
    for _ in range(days):
        best = np.full(shape, -1.0); act = np.zeros(shape, int)
        for code, outs in table.items():
            val = np.zeros(shape)
            for dlt, pr in outs:
                bb = np.clip(B + dlt, g.F_BMIN, g.F_BMAX)
                fail = (B + dlt) <= floor
                pk2 = np.minimum(np.maximum(PK, np.clip(bb, 0, None)), g.BUFFER)
                amt = np.clip(bb - g.BUFFER, 0, None)
                amt = np.where(N >= g.LIVE_AFTER, amt, np.minimum(amt, g.CAP_UNITS))
                b2 = bb - amt; n2 = np.where(amt > 0, np.minimum(N + 1, g.LIVE_AFTER), N)
                val += pr * np.where(fail, 0.0, amt * 100 * 0.9 + V[b2 - g.F_BMIN, pk2, n2])
            val = np.where(valid, val, -1.0)
            better = val > best + 1e-12
            best = np.where(better, val, best); act = np.where(better, code, act)
        V = np.where(valid, np.maximum(best, 0.0), 0.0)
    return act


def replay(h, l, c, prod: str, pe, pf, fixed_n: int | None = None, window: int = HORIZON) -> dict:
    """a02_real.sequential's replay mode with the contract count taken from each day's action (or fixed_n with a
    fair-odds A01 policy whose codes carry no size). Stops at the stop price. Tradeify rules as there."""
    rt = PLANS[prod]["rt"]
    S = len(c); starts = np.arange(0, S - window); A = len(starts)
    phase = np.zeros(A, int); eq = np.full(A, START); pk = eq.copy(); best = np.zeros(A); npay = np.zeros(A, int)
    fees = np.full(A, FEE); paid = np.zeros(A); first = np.full(A, -1)
    for d in range(window):
        idx = starts + d
        ev = phase == 0
        b_e = np.clip(np.rint((eq - START) / 100).astype(int), g.B_MIN, g.B_MAX)
        pk_e = np.maximum(np.clip(np.rint((pk - START) / 100).astype(int), 0, g.B_MAX), np.maximum(b_e, 0))
        bd_e = np.clip(np.rint(best / 100).astype(int), 0, g.BD_MAX)
        b_f = np.clip(np.rint((eq - START) / 100).astype(int), g.F_BMIN, g.F_BMAX)
        pk_f = np.maximum(np.clip(np.rint((pk - START) / 100).astype(int), 0, g.BUFFER), np.clip(b_f, 0, g.BUFFER))
        a = np.where(ev, pe[b_e - g.B_MIN, pk_e, bd_e], pf[b_f - g.F_BMIN, pk_f, np.minimum(npay, g.LIVE_AFTER)])
        if fixed_n is None:
            n, W, L = _decode(a)
        else:
            n = np.full(A, fixed_n); W, L = a // 100, a % 100
        W = W * 100.0; L = L * 100.0
        floor = np.where(ev, pk - 2000, np.where(pk >= START + 2000, START, pk - 2000))
        L = np.minimum(L, np.maximum(eq - floor - 1, 1))
        trade = a > 0
        finished = ~trade                     # an untradable (floor-adjacent) state: the account is finished (a02_real)
        n = np.maximum(n, 1).astype(np.float32)
        cost = rt * n
        hh, ll, cc = h[idx] * n[:, None], l[idx] * n[:, None], c[idx] * n[:, None]
        pnl, _, _ = a2._bracket_day(hh, ll, cc, np.where(trade, W + cost, 1e12), np.where(trade, np.maximum(L - cost, 1.0), 1e12))
        pnl = np.where(trade, pnl - cost, 0.0)
        ne = eq + pnl; br = (ne <= floor) | finished
        eq = ne; pk = np.maximum(pk, ne)
        best = np.where(ev, np.maximum(best, pnl), best)
        ok = ev & ~br & (eq - START >= 3000) & (best <= 0.40 * (eq - START))
        amt = np.where(~ev & ~br, np.maximum(eq - (START + 2000), 0.0), 0.0)
        amt = np.where(npay >= 3, amt, np.minimum(amt, 1250.0))
        paid += 0.9 * amt; first = np.where((amt > 0) & (first < 0), d + 1, first)
        eq -= amt; npay += amt > 0
        reset = br | ok
        phase = np.where(ok, 1, np.where(br, 0, phase))
        eq = np.where(reset, START, eq); pk = np.where(reset, START, pk)
        best = np.where(reset, 0.0, best); npay = np.where(reset, 0, npay)
        fees += np.where(br & (d + 1 < window), FEE, 0.0)
    net = paid - fees
    return {"p_any_payout": float((first > 0).mean()), "mean_net": float(net.mean()),
            "p_net_positive": float((net > 0).mean()), "mean_fees": float(fees.mean())}


def run(prod: str, train: str) -> dict:
    warnings.filterwarnings("ignore")
    test = "post" if train == "pre" else "pre"
    p = PLANS[prod]
    h, l, c, _ = a8.era_paths(train, prod, p["window"])
    table = outcome_table(h, l, c, prod); del h, l, c
    pe, pf = solve_eval(table), solve_funded(table)
    with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
        g.solve_all(21, keep_policy_at=21); g.solve_funded(21, "dollars", keep_policy_at=21)
    fe, ff = g.POLICY["eval"], g.POLICY["funded"]
    h, l, c, _ = a8.era_paths(test, prod, p["window"])
    base = replay(h, l, c, prod, fe, ff, fixed_n=p["fixed"])
    size = replay(h, l, c, prod, pe, pf)
    tr = a8.era_paths(train, prod, p["window"])                          # in-sample, for reference only
    size_in = replay(*tr[:3], prod, pe, pf)
    n0, w0, l0 = _decode(int(pe[0 - g.B_MIN, 0, 0])); nf, wf, lf = _decode(int(pf[0 - g.F_BMIN, 0, 0]))
    ns = [_decode(int(x))[0] for x in np.unique(pe[pe > 0])]
    r = {"product": prod, "train": train, "test": test, "fixed_fair_odds": base, "size_policy": size,
         "size_policy_in_sample": size_in, "eval_first_action": [n0, w0 * 100, l0 * 100],
         "funded_first_action": [nf, wf * 100, lf * 100], "sizes_used_eval": sorted(set(ns)),
         "beats_fixed": bool(size["mean_net"] > base["mean_net"] and size["p_any_payout"] > base["p_any_payout"])}
    print(json.dumps(r), flush=True)
    return r


def _out(prod: str, train: str) -> Path:
    return ROOT / "reports" / f"a13_{prod}_{train}.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", choices=tuple(PLANS)); ap.add_argument("--train", choices=("pre", "post"))
    ap.add_argument("--log", action="store_true")
    a = ap.parse_args(argv)
    if a.product:
        _out(a.product, a.train).write_text(json.dumps(run(a.product, a.train), indent=1) + "\n"); return 0
    r = {f"{p} train {t}": json.loads(_out(p, t).read_text()) for p in PLANS for t in ("pre", "post")}
    r["adopt"] = {p: all(r[f"{p} train {t}"]["beats_fixed"] for t in ("pre", "post")) for p in PLANS}
    OUT.write_text(json.dumps(r, indent=1) + "\n")
    for p in PLANS:
        for t in ("pre", "post"):
            _out(p, t).unlink()
    print(json.dumps(r["adopt"]))
    if a.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(trial_id=log.next_id("m"), hypothesis_id="A-series", symbol="MNQ+MGC",
                               date_range=("2011-02-01", "2026-08-27"), status="completed", params={"kind": "size_aware_policy", **r},
                               note="kind=computation; NOT a trial. A13: staking re-solved over (take, stop, contracts), cross-history. decisions.md 113."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
