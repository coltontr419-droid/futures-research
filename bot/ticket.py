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


FUNDED_STOP = 0.7      # decisions.md 814-815: under Tradeify's V2 payouts a funded stop of 0.7x the policy's is better with or without an edge


def ticket(phase: str, balance: float, peak: float, best: float = 0.0, payouts: int = 0, product: str = "MNQ",
           side: str = "long") -> dict:
    from accounts import base
    P = policy()
    p = P["PRODUCTS"][base(product)]; n = p["n"]; START = P["START"]
    peak = max(peak, balance)
    k = 1
    if phase == "live":                           # decisions.md 653, 657: $0 start, $2,000 trailing locking at $0, k x contracts
        b = _clip(int(round(balance / 100)), P["L_MIN"], P["L_MAX"])
        pk = max(_clip(int(round(peak / 100)), 0, P["L_LOCK"]), _clip(b, 0, P["L_LOCK"]))
        a = P["LIVE"][base(product)][b - P["L_MIN"]][pk]
        floor = 0.0 if peak >= 100 * P["L_LOCK"] else peak - 100 * P["L_LOCK"]
        k = P["LIVE_K"].get(base(product), 1)
    elif phase == "eval":
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
    n = n * k
    room = balance - floor
    if room <= p["rt"] * n + 10:
        return {"trade": False, "finished": True, "floor": floor, "live": phase == "live"}
    if a <= 0:
        return {"trade": False, "floor": floor}
    W = (a // 100) * 100.0 * k
    L = min((a % 100) * 100.0 * k * (FUNDED_STOP if phase == "funded" else 1.0), max(balance - floor - 1, 1))
    cost = p["rt"] * n
    return {"trade": True, "product": product, "side": side, "contracts": n, "entry": p["entry"], "exit": p["exit"],
            "take_net": W, "stop_net": L, "floor": floor,
            "take_points": _pts(W + cost, n, p), "stop_points": _pts(max(L - cost, 1.0), n, p)}


def _usd(x: float) -> str:
    return f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}"


def _ticks(points: float, product: str) -> int:
    """Points as a whole number of the instrument's ticks - what TradingView's bracket fields take."""
    from accounts import base
    return int(round(points / policy()["PRODUCTS"][base(product)]["tick"]))


def describe(t: dict, product: str, entry_txt: str | None = None, exit_txt: str | None = None) -> str:
    """The ticket's instructions. entry_txt / exit_txt: display times (Chicago, 12-hour, decisions.md 491); default the window's
    local clock as stored in the ticket."""
    if t.get("finished") and t.get("live"):
        return (f"**{product}: LIVE ACCOUNT FINISHED** - within one day's costs of its floor ({_usd(t['floor'])}). No trade; it ends here.")
    if t.get("finished"):
        return (f"**{product}: ACCOUNT FINISHED** - within one day's costs of the floor ({_usd(t['floor'])}); any trade "
                f"breaches it. Start a new evaluation (`!new {product}`).")
    if not t["trade"]:
        return f"**{product}: no trade today.** Floor {_usd(t['floor'])}."
    up, dn = ("+", "-") if t["side"] == "long" else ("-", "+")
    verb = "BUY" if t["side"] == "long" else "SELL"
    from accounts import base
    tz = policy()["PRODUCTS"][base(product)].get("tz", "ET")
    ent = entry_txt or f"{t['entry']} {tz}"; ext = exit_txt or f"{t['exit']} {tz}"
    return (f"**{product}** - {ent}: **{verb} {t['contracts']} {base(product)}** at market, then one OCO bracket on the fill:\n"
            f"> take-profit: fill {up} **{t['take_points']:.2f}** pts = **{_ticks(t['take_points'], product)} ticks** (~ +${t['take_net']:,.0f} net)\n"
            f"> stop: fill {dn} **{t['stop_points']:.2f}** pts = **{_ticks(t['stop_points'], product)} ticks** (~ -${t['stop_net']:,.0f} net)\n"
            f"> {ext}: if neither filled, close at market. Floor today {_usd(t['floor'])}.")
