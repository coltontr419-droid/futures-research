"""A06 - the A01/A03 solved staking policy as a daily order ticket, for the demo forward test. decisions.md 104.

    python -m futuresres.reporting.a06_playbook eval   --balance 50300 --peak 50300 --best 300
    python -m futuresres.reporting.a06_playbook funded --balance 51200 --peak 51200 --payouts 0
    python -m futuresres.reporting.a06_playbook table          # writes reports/a06_playbook_{eval,funded}.csv

The trade, exactly as replayed in A03 (a02_real.sequential): at 09:30 ET buy 2 MNQ at market; one OCO bracket -
take-profit +W, stop -L in NET dollars (the order offsets add/subtract the $4.64 round trip, as A02 does); flat
at 16:00 ET if neither fills. A state with no trade (policy 0) means stand aside. Inputs are the account's
END-OF-DAY figures from yesterday: balance, the highest end-of-day balance (the trailing floor's peak), and in
the evaluation the best single day's profit so far (the 40% consistency rule); in funded, payouts taken.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.a01_game as g

ROOT = Path(__file__).resolve().parents[3]
START = 50_000.0
CONTRACTS = 2
MULT = 2.0                      # MNQ $ per point
COST = 2.32 * CONTRACTS
TICK = 0.25


def _solve():
    if "eval" not in g.POLICY:
        with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
            g.solve_all(21, keep_policy_at=21)
            g.solve_funded(21, "dollars", keep_policy_at=21)
    return g.POLICY["eval"], g.POLICY["funded"]


def _pts(usd: float) -> float:
    return round(usd / (CONTRACTS * MULT) / TICK) * TICK


def ticket(phase: str, balance: float, peak: float, best: float = 0.0, payouts: int = 0) -> dict:
    """The day's order, by the same state rounding and stop cap as a02_real.sequential."""
    pe, pf = _solve()
    peak = max(peak, balance)
    if phase == "eval":
        b = int(np.clip(np.rint((balance - START) / 100), g.B_MIN, g.B_MAX))
        pk = max(int(np.clip(np.rint((peak - START) / 100), 0, g.B_MAX)), max(b, 0))
        bd = int(np.clip(np.rint(best / 100), 0, g.BD_MAX))
        a = int(pe[b - g.B_MIN, pk, bd])
        floor = peak - 2000
    else:
        b = int(np.clip(np.rint((balance - START) / 100), g.F_BMIN, g.F_BMAX))
        pk = max(int(np.clip(np.rint((peak - START) / 100), 0, g.BUFFER)), int(np.clip(b, 0, g.BUFFER)))
        a = int(pf[b - g.F_BMIN, pk, min(payouts, g.LIVE_AFTER)])
        floor = START if peak >= START + 2000 else peak - 2000
    if a <= 0:
        return {"trade": False, "floor": floor}
    W = (a // 100) * 100.0
    L = min((a % 100) * 100.0, max(balance - floor - 1, 1))
    return {"trade": True, "take_net": W, "stop_net": L, "floor": floor,
            "take_points": _pts(W + COST), "stop_points": _pts(max(L - COST, 1.0))}


def _print(t: dict) -> None:
    if not t["trade"]:
        print(f"NO TRADE today (stand aside). Floor ${t['floor']:,.0f}.")
        return
    print(f"09:30 ET: BUY {CONTRACTS} MNQ at market, then one OCO bracket on the fill price:\n"
          f"  take-profit  fill + {t['take_points']:.2f} pts   (≈ +${t['take_net']:,.0f} net)\n"
          f"  stop         fill - {t['stop_points']:.2f} pts   (≈ -${t['stop_net']:,.0f} net)\n"
          f"16:00 ET: if neither filled, close at market.   Floor today ${t['floor']:,.0f}.")


def table() -> None:
    """Every reachable state's ticket, for reference without Python."""
    rows = ["balance,peak,best_day,trade,take_net,stop_net,take_points,stop_points"]
    for b in range(-19, 30):
        for pk in range(max(b, 0), min(b + 20, 30)):
            for bd in range(0, 13):
                if bd > max(pk, 0):
                    continue
                t = ticket("eval", START + 100 * b, START + 100 * pk, 100 * bd)
                rows.append(f"{START+100*b:.0f},{START+100*pk:.0f},{100*bd},{int(t['trade'])},"
                            + (f"{t['take_net']:.0f},{t['stop_net']:.0f},{t['take_points']},{t['stop_points']}" if t["trade"] else ",,,"))
    (ROOT / "reports" / "a06_playbook_eval.csv").write_text("\n".join(rows) + "\n")
    rows = ["balance,peak,payouts,trade,take_net,stop_net,take_points,stop_points"]
    for b in range(-19, 21):
        for pk in range(max(b, 0), 21):
            if pk - b >= 20 and pk < 20:
                continue
            for n in range(0, g.LIVE_AFTER + 1):
                t = ticket("funded", START + 100 * b, START + 100 * pk, payouts=n)
                rows.append(f"{START+100*b:.0f},{START+100*pk:.0f},{n},{int(t['trade'])},"
                            + (f"{t['take_net']:.0f},{t['stop_net']:.0f},{t['take_points']},{t['stop_points']}" if t["trade"] else ",,,"))
    (ROOT / "reports" / "a06_playbook_funded.csv").write_text("\n".join(rows) + "\n")
    print("wrote reports/a06_playbook_eval.csv, reports/a06_playbook_funded.csv")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.a06_playbook")
    ap.add_argument("phase", choices=("eval", "funded", "table"))
    ap.add_argument("--balance", type=float, default=START); ap.add_argument("--peak", type=float, default=None)
    ap.add_argument("--best", type=float, default=0.0); ap.add_argument("--payouts", type=int, default=0)
    a = ap.parse_args(argv)
    if a.phase == "table":
        table(); return 0
    _print(ticket(a.phase, a.balance, a.peak if a.peak is not None else a.balance, a.best, a.payouts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
