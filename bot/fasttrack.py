"""Bulenox Fast Track 100K (Option 1): the daily bracket tickets and the account's payout checks, in plain Python for the droplet.
Not wired into futures_bot.py yet (decisions.md §1144); the user funds Fast Track after the NKD payout. Plans: decisions.md §1098-§1112,
§1123-§1131 (take $800 / stop $4,000, always long, one account per slot). Terms: Bulenox help centre, 2026-10-29 (§1098, §1105, §1109).
"""

from __future__ import annotations

START = 100_000.0
DD, LOCK = 4_000.0, 100.0                       # trailing drawdown (intraday, open P&L included); the floor locks at START + $100
GOAL1, GOALN = 6_000.0, 3_000.0                 # profit since the last payout needed for the 1st / later requests
CONS = (0.20, 0.25, 0.30)                       # best day <= this share of the cycle's profit (1st, 2nd, 3rd+ request)
CAPS = (2_500.0, 2_500.0, 2_500.0, 3_000.0)     # request caps: payouts 1-3, then 4+
PMIN, SPLIT, TRANSITION_AT = 1_000.0, 0.90, 3   # after the 3rd payout Bulenox may move the account to a live Funded Account

# One bracket a day per slot, always long. Points from $800 / $4,000 over 7 contracts (MNQ $2/pt, MGC $10/pt), rounded to the tick.
SLOTS = {
    "MNQ day":  {"symbol": "MNQ", "qty": 7, "take": 57.25, "stop": 285.75, "entry_ct": "08:30", "flat_ct": "15:00",
                 "days": "Mon-Fri", "note": "the 9:30 ET open; flat by 3:00 PM CT"},
    "MNQ full": {"symbol": "MNQ", "qty": 7, "take": 57.25, "stop": 285.75, "entry_ct": "17:01", "flat_ct": "15:55",
                 "days": "Sun-Thu evening", "note": "first bar after the 5:00 PM CT reopen; flat by 3:55 PM CT next day"},
    "MGC full": {"symbol": "MGC", "qty": 7, "take": 11.4, "stop": 57.1, "entry_ct": "17:01", "flat_ct": "15:55",
                 "days": "Sun-Thu evening", "note": "first bar after the 5:00 PM CT reopen; flat by 3:55 PM CT next day"},
}


def floor(peak: float) -> float:
    """Liquidation level as P&L from START: trails the peak by DD and stops rising at +LOCK."""
    return min(peak - DD, LOCK)


def ticket(slot: str, balance: float, peak: float) -> dict:
    """Today's bracket. Skipped (with the reason) if the account is at or below its floor or the stop would breach it at entry."""
    s = SLOTS[slot]; pnl, pk = balance - START, max(peak, balance) - START
    room = pnl - floor(pk)
    risk = s["qty"] * s["stop"] * (2.0 if s["symbol"] == "MNQ" else 10.0)
    out = {"slot": slot, **s, "side": "BUY", "room": round(room, 2), "risk": round(risk, 2)}
    if room <= 0:
        out["skip"] = "account at or below its floor: closed"
    elif risk > room + 1e-9:
        out["warn"] = f"the stop risks ${risk:,.0f} with ${room:,.0f} of room: a full stop-out ends the account (the plan accepts this)"
    return out


def payout(balance: float, cycle_profit: float, best_day: float, npay: int) -> dict:
    """Can a request be made today, and for how much (before the 90% split)?"""
    goal = GOAL1 if npay == 0 else GOALN
    cons = CONS[min(npay, len(CONS) - 1)]
    amt = min(balance - START - LOCK, CAPS[min(npay, len(CAPS) - 1)])
    why = []
    if cycle_profit < goal:
        why.append(f"profit since last payout ${cycle_profit:,.0f} < ${goal:,.0f}")
    if cycle_profit > 0 and best_day > cons * cycle_profit:
        why.append(f"best day ${best_day:,.0f} > {cons:.0%} of ${cycle_profit:,.0f} (need ${best_day / cons:,.0f} of cycle profit)")
    if amt < PMIN:
        why.append(f"request ${amt:,.0f} < ${PMIN:,.0f} minimum")
    ok = not why
    return {"eligible": ok, "amount": round(amt, 2) if ok else 0.0, "to_you": round(amt * SPLIT, 2) if ok else 0.0, "why_not": why,
            "transition_next": ok and npay + 1 >= TRANSITION_AT}
