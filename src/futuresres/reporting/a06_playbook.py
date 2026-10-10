"""A06 - the A01/A03 solved staking policy as a daily order ticket, for the demo forward test. decisions.md 104.

    python -m futuresres.reporting.a06_playbook eval   --balance 50300 --peak 50300 --best 300
    python -m futuresres.reporting.a06_playbook funded --balance 51200 --peak 51200 --payouts 0
    python -m futuresres.reporting.a06_playbook eval --product MGC --side long --balance 50000   # gold (8 MGC, 03:00-11:30 ET);
                                                     # --side from `python -m futuresres.signals.z08 --direction`, weekly
    python -m futuresres.reporting.a06_playbook eval --product MCL --balance 50000   # the crude account (10 MCL, 18:00-16:55 ET)
    python -m futuresres.reporting.a06_playbook table [--product MGC|MCL]   # writes reports/a06_playbook_{eval,funded}[_mgc].csv

The trade, exactly as replayed in A03 (a02_real.sequential): at 09:30 ET buy 4 MNQ (default; decisions.md 105) at market; one OCO bracket -
take-profit +W, stop -L in NET dollars (the order offsets add/subtract the round trips, $2.32 a contract, as A02 does); flat
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
#: per product: default size, $ per point, round trip per contract, tick, entry and exit (ET).
#: MNQ 4 - decisions.md 105 (beats A03's 2 on both histories). MGC 8 London long - decisions.md 106 (the Y03
#: gold cell; 8 matches 4 MNQ's daily $ swing; near-uncorrelated with the MNQ account).
PRODUCTS = {"MNQ": {"n": 4, "mult": 2.0, "rt": 2.32, "tick": 0.25, "entry": "09:30", "exit": "16:00"},
            "MGC": {"n": 8, "mult": 10.0, "rt": 3.32, "tick": 0.10, "entry": "03:00", "exit": "11:30"},
            # decisions.md 116: 10 MCL, the whole session (enter at the 18:00 ET open, flat by 16:55 ET)
            "MCL": {"n": 10, "mult": 100.0, "rt": 3.32, "tick": 0.01, "entry": "18:00", "exit": "16:55"}}
CONTRACTS = PRODUCTS["MNQ"]["n"]


def _solve():
    if "eval" not in g.POLICY:
        with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
            g.solve_all(21, keep_policy_at=21)
            g.solve_funded(21, "dollars", keep_policy_at=21)
    return g.POLICY["eval"], g.POLICY["funded"]


def _pts(usd: float, n: int, p: dict) -> float:
    return round(round(usd / (n * p["mult"]) / p["tick"]) * p["tick"], 2)


def ticket(phase: str, balance: float, peak: float, best: float = 0.0, payouts: int = 0, n: int | None = None,
           product: str = "MNQ", side: str = "long") -> dict:
    """The day's order, by the same state rounding and stop cap as a02_real.sequential."""
    pe, pf = _solve()
    p = PRODUCTS[product]; n = n or p["n"]
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
    room = balance - floor
    if room <= p["rt"] * n + 10:              # commissions + ~$10 slippage alone would breach (decisions.md 108)
        return {"trade": False, "finished": True, "floor": floor}
    if a <= 0:
        return {"trade": False, "floor": floor}
    W = (a // 100) * 100.0
    L = min((a % 100) * 100.0, max(balance - floor - 1, 1))
    cost = p["rt"] * n
    return {"trade": True, "product": product, "side": side, "contracts": n, "entry": p["entry"], "exit": p["exit"],
            "take_net": W, "stop_net": L, "floor": floor,
            "take_points": _pts(W + cost, n, p), "stop_points": _pts(max(L - cost, 1.0), n, p)}


def _print(t: dict) -> None:
    if t.get("finished"):
        print(f"ACCOUNT FINISHED: within one day's costs of the floor (${t['floor']:,.0f}); any trade breaches it. "
              f"Start a new evaluation.")
        return
    if not t["trade"]:
        print(f"NO TRADE today (stand aside). Floor ${t['floor']:,.0f}.")
        return
    up, dn = ("+", "-") if t["side"] == "long" else ("-", "+")
    print(f"{t['entry']} ET: {'BUY' if t['side'] == 'long' else 'SELL'} {t['contracts']} {t['product']} at market, then one OCO bracket on the fill price:\n"
          f"  take-profit  fill {up} {t['take_points']:.2f} pts   (≈ +${t['take_net']:,.0f} net)\n"
          f"  stop         fill {dn} {t['stop_points']:.2f} pts   (≈ -${t['stop_net']:,.0f} net)\n"
          f"{t['exit']} ET: if neither filled, close at market.   Floor today ${t['floor']:,.0f}.")


def table(product: str = "MNQ") -> None:
    """Every reachable state's ticket, for reference without Python."""
    rows = ["balance,peak,best_day,trade,take_net,stop_net,take_points,stop_points"]
    for b in range(-19, 30):
        for pk in range(max(b, 0), min(b + 20, 30)):
            for bd in range(0, 13):
                if bd > max(pk, 0):
                    continue
                t = ticket("eval", START + 100 * b, START + 100 * pk, 100 * bd, product=product)
                rows.append(f"{START+100*b:.0f},{START+100*pk:.0f},{100*bd},{int(t['trade'])},"
                            + (f"{t['take_net']:.0f},{t['stop_net']:.0f},{t['take_points']},{t['stop_points']}" if t["trade"] else ",,,"))
    sfx = "" if product == "MNQ" else f"_{product.lower()}"
    (ROOT / "reports" / f"a06_playbook_eval{sfx}.csv").write_text("\n".join(rows) + "\n")
    rows = ["balance,peak,payouts,trade,take_net,stop_net,take_points,stop_points"]
    for b in range(-19, 21):
        for pk in range(max(b, 0), 21):
            if pk - b >= 20 and pk < 20:
                continue
            for n in range(0, g.LIVE_AFTER + 1):
                t = ticket("funded", START + 100 * b, START + 100 * pk, payouts=n, product=product)
                rows.append(f"{START+100*b:.0f},{START+100*pk:.0f},{n},{int(t['trade'])},"
                            + (f"{t['take_net']:.0f},{t['stop_net']:.0f},{t['take_points']},{t['stop_points']}" if t["trade"] else ",,,"))
    (ROOT / "reports" / f"a06_playbook_funded{sfx}.csv").write_text("\n".join(rows) + "\n")
    print(f"wrote reports/a06_playbook_eval{sfx}.csv, reports/a06_playbook_funded{sfx}.csv")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.a06_playbook")
    ap.add_argument("phase", choices=("eval", "funded", "table"))
    ap.add_argument("--balance", type=float, default=START); ap.add_argument("--peak", type=float, default=None)
    ap.add_argument("--best", type=float, default=0.0); ap.add_argument("--payouts", type=int, default=0)
    ap.add_argument("--contracts", type=int, default=None)
    ap.add_argument("--product", choices=tuple(PRODUCTS), default="MNQ")
    ap.add_argument("--side", choices=("long", "short"), default="long",
                    help="MGC: this week's direction from `python -m futuresres.signals.z08 --direction` (decisions.md 117)")
    a = ap.parse_args(argv)
    if a.phase == "table":
        table(a.product); return 0
    _print(ticket(a.phase, a.balance, a.peak if a.peak is not None else a.balance, a.best, a.payouts, a.contracts, a.product, a.side))
    return 0


if __name__ == "__main__":
    sys.exit(main())
