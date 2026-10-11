"""The daily order ticket in plain Python - a line-for-line port of futuresres.reporting.a06_playbook.ticket that
reads the exported policy (bot/policy.json) instead of solving. No numpy, no solver: it runs on the droplet.
tests/test_bot_ticket.py checks it against the playbook on thousands of random states. decisions.md 123.
"""

from __future__ import annotations

import json
from pathlib import Path

_POLICY: dict | None = None


def policy(path: Path | None = None) -> dict:
    global _POLICY
    if _POLICY is None:
        _POLICY = json.loads((path or Path(__file__).with_name("policy.json")).read_text())
    return _POLICY


def _clip(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, x))


def _pts(usd: float, n: int, p: dict) -> float:
    return round(round(usd / (n * p["mult"]) / p["tick"]) * p["tick"], 2)


def ticket(phase: str, balance: float, peak: float, best: float = 0.0, payouts: int = 0, product: str = "MNQ",
           side: str = "long") -> dict:
    P = policy()
    p = P["PRODUCTS"][product]; n = p["n"]; START = P["START"]
    peak = max(peak, balance)
    if phase == "eval":
        b = _clip(int(round((balance - START) / 100)), P["B_MIN"], P["B_MAX"])
        pk = max(_clip(int(round((peak - START) / 100)), 0, P["B_MAX"]), max(b, 0))
        bd = _clip(int(round(best / 100)), 0, P["BD_MAX"])
        a = P["eval"][b - P["B_MIN"]][pk][bd]
        floor = peak - 2000
    else:
        b = _clip(int(round((balance - START) / 100)), P["F_BMIN"], P["F_BMAX"])
        pk = max(_clip(int(round((peak - START) / 100)), 0, P["BUFFER"]), _clip(b, 0, P["BUFFER"]))
        a = P["funded"][b - P["F_BMIN"]][pk][min(payouts, P["LIVE_AFTER"])]
        floor = START if peak >= START + 2000 else peak - 2000
    room = balance - floor
    if room <= p["rt"] * n + 10:
        return {"trade": False, "finished": True, "floor": floor}
    if a <= 0:
        return {"trade": False, "floor": floor}
    W = (a // 100) * 100.0
    L = min((a % 100) * 100.0, max(balance - floor - 1, 1))
    cost = p["rt"] * n
    return {"trade": True, "product": product, "side": side, "contracts": n, "entry": p["entry"], "exit": p["exit"],
            "take_net": W, "stop_net": L, "floor": floor,
            "take_points": _pts(W + cost, n, p), "stop_points": _pts(max(L - cost, 1.0), n, p)}


def describe(t: dict, product: str) -> str:
    if t.get("finished"):
        return (f"**{product}: ACCOUNT FINISHED** - within one day's costs of the floor (${t['floor']:,.0f}); any trade "
                f"breaches it. Start a new evaluation (`!new {product}`).")
    if not t["trade"]:
        return f"**{product}: no trade today.** Floor ${t['floor']:,.0f}."
    up, dn = ("+", "-") if t["side"] == "long" else ("-", "+")
    verb = "BUY" if t["side"] == "long" else "SELL"
    return (f"**{product}** - {t['entry']} ET: **{verb} {t['contracts']} {product}** at market, then one OCO bracket on the fill:\n"
            f"> take-profit: fill {up} **{t['take_points']:.2f}** pts (~ +${t['take_net']:,.0f} net)\n"
            f"> stop: fill {dn} **{t['stop_points']:.2f}** pts (~ -${t['stop_net']:,.0f} net)\n"
            f"> {t['exit']} ET: if neither filled, close at market. Floor today ${t['floor']:,.0f}.")
