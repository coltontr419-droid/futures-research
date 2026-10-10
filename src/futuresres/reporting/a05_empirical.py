"""A05 - re-solve the account game with REAL bracket outcome distributions, learned on 2015-2020 MNQ
sessions and tested on 2021-2026. A COMPUTATION; zero edge (drift removed); no trial. decisions.md 102.

    python -m futuresres.reporting.a05_empirical [--log]

A01 priced each bracket as a fair two-outcome coin. On real minute paths a bracket can also end at the
close with neither level hit, stops can gap, and the take/stop split differs from fair. Here every
bracket's NET outcome distribution (2 MNQ, 09:30-16:00, orders netted for the $4.64 cost as in A02) is
measured on the TRAIN sessions (2015-11 to 2020-12, drift removed within that era), binned to $100, and
the evaluation and funded games are re-solved with those distributions. The resulting policy tables are
then run through A03's test: back-to-back $80 attempts for 84 trading days, real 2021-2026 sessions in
order, from every start date - against A01's fair-odds policy on the same test.
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
import futuresres.reporting.y01_structure_ev as y
import futuresres.reporting.y03_sessions as s3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a05_empirical.json"
CONTRACTS = 2
RT1 = 2.32
MIN_P = 1e-3
#: a reduced bracket menu for the multi-outcome solve (speed); A01's fair-odds baseline keeps its full grid,
#: so any gain A05 shows is despite a smaller menu
W_A05 = (4, 6, 8, 10, 12, 15, 20)
L_A05 = (5, 8, 10)


def train_paths():
    """2 MNQ $ paths, 09:30-16:00, 2015-11 to 2020-12, drift removed within the era. No cost inside."""
    spec = s3.PRODUCTS["MNQ"]
    y.SERIES = y.ROOT / "data" / "continuous" / f"{spec['series']}.parquet"
    y.MULT = spec["mult"]; y.WINDOWS.update(s3.WINDOWS)
    dates, H, L, C, notional = y.load_sessions()
    pre = dates < y.ERA
    h, l, c, _ = y.window_paths(H[pre], L[pre], C[pre], "rth_0930_1600", None)
    n = np.float32(CONTRACTS)
    return (h * notional * n).astype(np.float32), (l * notional * n).astype(np.float32), (c * notional * n).astype(np.float32)


def outcome_table(paths) -> dict:
    """For each bracket (W, L) in A01's grid: {delta in $100 units: probability}, NET of cost."""
    h, l, c = paths
    cost = RT1 * CONTRACTS
    S = len(c)
    table = {}
    for W in W_A05:
        for L in L_A05:
            Wd, Ld = np.full(S, W * 100.0 + cost), np.full(S, max(L * 100.0 - cost, 1.0))
            pnl, _, _ = a2._bracket_day(h, l, c, Wd, Ld)
            net = pnl - cost
            units = np.clip(np.rint(net / 100).astype(int), -2 * g.DAILY, g.B_MAX)
            vals, cnt = np.unique(units, return_counts=True)
            p = cnt / S
            keep = p >= MIN_P
            p = p[keep] / p[keep].sum()
            table[(W, L)] = list(zip(vals[keep].tolist(), p.tolist()))
    return table


def solve_eval(table, days: int = 21) -> np.ndarray:
    nb = g.B_MAX - g.B_MIN + 1
    b_val = (np.arange(nb)[:, None, None] + g.B_MIN)
    pk = np.arange(g.B_MAX + 1)[None, :, None]; bd = np.arange(g.BD_MAX + 1)[None, None, :]
    shape = (nb, g.B_MAX + 1, g.BD_MAX + 1)
    B = np.broadcast_to(b_val, shape); PK = np.broadcast_to(pk, shape); BD = np.broadcast_to(bd, shape)
    valid = (PK >= np.maximum(B, 0)) & (B > PK - g.DD)
    V = np.zeros(shape); act = np.zeros(shape, int)
    for _ in range(days):
        best = np.full(shape, -1.0); act = np.zeros(shape, int)
        for (W, L), outs in table.items():
            val = np.zeros(shape)
            for dlt, p in outs:
                nb_ = B + dlt
                fail = nb_ <= PK - g.DD
                nb_c = np.clip(nb_, g.B_MIN, g.B_MAX)
                npk = np.minimum(np.maximum(PK, nb_c), g.B_MAX)
                nbd = np.minimum(np.maximum(BD, max(dlt, 0)), g.BD_MAX)
                passed = (nb_c >= g.TARGET) & (np.maximum(BD, max(dlt, 0)) <= g.CONS * nb_c)
                v = np.where(fail, 0.0, np.where(passed, 1.0, V[nb_c - g.B_MIN, npk, nbd]))
                val += p * v
            val = np.where(valid, val, -1.0)
            better = val > best + 1e-12
            best = np.where(better, val, best); act = np.where(better, W * 100 + L, act)
        V = np.where(valid, np.maximum(best, 0.0), 0.0)
    return act


def solve_funded(table, days: int = 21) -> np.ndarray:
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
        for (W, L), outs in table.items():
            val = np.zeros(shape)
            for dlt, p in outs:
                bb = np.clip(B + dlt, g.F_BMIN, g.F_BMAX)
                fail = (B + dlt) <= floor
                pk2 = np.minimum(np.maximum(PK, np.clip(bb, 0, None)), g.BUFFER)
                amt = np.clip(bb - g.BUFFER, 0, None)
                amt = np.where(N >= g.LIVE_AFTER, amt, np.minimum(amt, g.CAP_UNITS))
                b2 = bb - amt; n2 = np.where(amt > 0, np.minimum(N + 1, g.LIVE_AFTER), N)
                v = np.where(fail, 0.0, amt * 100 * 0.9 + V[b2 - g.F_BMIN, pk2, n2])
                val += p * v
            val = np.where(valid, val, -1.0)
            better = val > best + 1e-12
            best = np.where(better, val, best); act = np.where(better, W * 100 + L, act)
        V = np.where(valid, np.maximum(best, 0.0), 0.0)
    return act


def run() -> dict:
    warnings.filterwarnings("ignore")
    tp = train_paths()
    table = outcome_table(tp)
    del tp
    fair = {}
    for (W, L), outs in table.items():                      # the fair benchmark, for the record
        fair[f"{W*100}/{L*100}"] = {"p_take": float(sum(p for d, p in outs if d >= W)),
                                    "p_stop": float(sum(p for d, p in outs if d <= -L)),
                                    "fair_take": L / (W + L)}
    pe = solve_eval(table); pf = solve_funded(table)
    out = {"train": "MNQ 09:30-16:00, 2015-11 to 2020-12, drift removed",
           "bracket_odds_sample": {k: fair[k] for k in ("1200/1000", "1000/1000", "600/1000", "1500/500") if k in fair}}
    with contextlib.redirect_stdout(io.StringIO()):
        g.solve_all(21, keep_policy_at=21); g.solve_funded(21, "dollars", keep_policy_at=21)
    fair_pe, fair_pf = g.POLICY["eval"].copy(), g.POLICY["funded"].copy()
    for name, (e, f) in (("A01 fair-odds policy", (fair_pe, fair_pf)), ("A05 real-odds policy", (pe, pf))):
        g.POLICY["eval"], g.POLICY["funded"] = e, f
        r = a2.sequential(CONTRACTS, "replay")
        out[name] = r
        print(name, json.dumps(r), flush=True)
    first_e = int(pe[0 - g.B_MIN, 0, 0]); out["A05_first_day_bracket"] = [first_e // 100 * 100, first_e % 100 * 100]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--log", action="store_true")
    a = ap.parse_args(argv)
    r = json.loads(OUT.read_text()) if (a.log and OUT.exists()) else run()
    OUT.write_text(json.dumps(r, indent=1, default=float) + "\n")
    if a.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(trial_id=log.next_id("m"), hypothesis_id="A-series", symbol="MNQ",
                               date_range=("2015-11-20", "2026-08-27"), status="completed",
                               params={"kind": "empirical_odds_policy", **r},
                               note="kind=computation; NOT a trial. A05: staking re-solved on 2015-2020 real bracket odds, tested 2021-2026. decisions.md 102."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
