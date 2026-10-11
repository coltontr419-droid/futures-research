"""Account bookkeeping for the demo: Tradeify Select Daily rules as the programme models them (decisions.md 81-82,
user's terms). One account per product; state in a JSON file; every event appended to a CSV demo log.
Plain Python; no Discord here, so it is testable on its own. decisions.md 123.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

START, TARGET, TRAIL, LOCK_AT, CONSISTENCY, CAP, LIVE_AFTER, FEE = 50_000.0, 3_000.0, 2_000.0, 52_000.0, 0.40, 1_250.0, 3, 80.0
PRODUCTS = ("MNQ", "MGC", "MCL")


def fresh(product: str) -> dict:
    return {"product": product, "phase": "eval", "balance": START, "peak": START, "best": 0.0, "payouts": 0,
            "evals_bought": 1, "fees": FEE, "paid": 0.0, "since": dt.date.today().isoformat()}


class Book:
    def __init__(self, state_path: Path, log_path: Path):
        self.state_path, self.log_path = Path(state_path), Path(log_path)
        self.s = json.loads(self.state_path.read_text()) if self.state_path.exists() else {p: fresh(p) for p in PRODUCTS}

    # ------------------------------------------------------------------ persistence
    def save(self) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.s, indent=1)); tmp.replace(self.state_path)

    def log(self, product: str, event: str, **kw) -> None:
        new = not self.log_path.exists()
        a = self.s[product]
        row = {"time": dt.datetime.now().isoformat(timespec="seconds"), "product": product, "event": event,
               "phase": a["phase"], "balance": a["balance"], "peak": a["peak"], "best_day": a["best"],
               "payouts": a["payouts"], **{k: kw.get(k, "") for k in ("amount", "pnl", "note")}}
        with self.log_path.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row)); new and w.writeheader(); w.writerow(row)

    # ------------------------------------------------------------------ rules
    @staticmethod
    def floor(a: dict) -> float:
        if a["phase"] == "eval":
            return a["peak"] - TRAIL                        # trails the EOD peak, never locks
        return START if a["peak"] >= LOCK_AT else a["peak"] - TRAIL

    def eod(self, product: str, balance: float) -> list[str]:
        """Record an end-of-day balance; returns the messages to post."""
        a = self.s[product]; msgs = []
        fl = self.floor(a)
        pnl = balance - a["balance"]
        a["balance"] = balance
        if balance <= fl:
            self.log(product, "EOD", pnl=pnl, note="breached floor")
            msgs.append(f"**{product} {a['phase']} FAILED** - closed ${balance:,.2f} at or below the floor ${fl:,.0f}. "
                        f"Buy a new evaluation and send `!new {product}`.")
            a["phase"] = "dead"; self.save(); return msgs
        a["peak"] = max(a["peak"], balance)
        if a["phase"] == "eval":
            a["best"] = max(a["best"], pnl)
            prof = balance - START
            self.log(product, "EOD", pnl=pnl)
            if prof >= TARGET and a["best"] <= CONSISTENCY * prof:
                msgs.append(f"**{product} PASSED** (profit ${prof:,.0f}, best day ${a['best']:,.0f}). Now trading the "
                            f"funded account from $50,000.")
                self.log(product, "PASSED")
                a.update(phase="funded", balance=START, peak=START, best=0.0, payouts=0)
            elif prof >= TARGET:
                need = a["best"] / CONSISTENCY
                msgs.append(f"{product}: target reached but the best day (${a['best']:,.0f}) is over 40% of profit - "
                            f"needs profit of ${need:,.0f} to pass.")
        else:
            self.log(product, "EOD", pnl=pnl)
            amt = max(balance - LOCK_AT, 0.0)
            if a["payouts"] < LIVE_AFTER:
                amt = min(amt, CAP)
            if amt > 0:
                msgs.append(f"**{product}: request a payout of ${amt:,.2f}** (you keep 90%: ${0.9 * amt:,.2f}). "
                            f"When paid, send `!payout {product} {amt:.2f}`.")
        self.save(); return msgs

    def payout(self, product: str, amount: float) -> str:
        a = self.s[product]
        a["balance"] -= amount; a["payouts"] += 1; a["paid"] += 0.9 * amount
        self.log(product, "PAYOUT", amount=amount); self.save()
        return f"{product}: payout ${amount:,.2f} recorded (#{a['payouts']}; you received ${0.9 * amount:,.2f}). Balance ${a['balance']:,.2f}."

    def new(self, product: str) -> str:
        prev = self.s[product]
        a = fresh(product)
        a["evals_bought"] = prev.get("evals_bought", 0) + 1; a["fees"] = prev.get("fees", 0.0) + FEE; a["paid"] = prev.get("paid", 0.0)
        self.s[product] = a
        self.log(product, "NEW_EVAL", amount=FEE); self.save()
        return f"{product}: new $50,000 evaluation started (evaluation #{a['evals_bought']}; fees so far ${a['fees']:,.0f})."

    def set(self, product: str, phase: str, balance: float, peak: float, best: float = 0.0, payouts: int = 0) -> str:
        a = self.s[product]
        a.update(phase=phase, balance=balance, peak=max(peak, balance), best=best, payouts=payouts)
        self.log(product, "SET", note=f"{phase} {balance} {peak} {best} {payouts}"); self.save()
        return f"{product}: state set - {phase}, balance ${balance:,.2f}, peak ${a['peak']:,.2f}, best day ${best:,.0f}, payouts {payouts}."

    def status(self) -> str:
        lines = []
        for p in PRODUCTS:
            a = self.s[p]
            net = a.get("paid", 0.0) - a.get("fees", 0.0)
            lines.append(f"**{p}** {a['phase']}: balance ${a['balance']:,.2f}, peak ${a['peak']:,.2f}, floor "
                         f"${self.floor(a) if a['phase'] != 'dead' else 0:,.0f}, best day ${a['best']:,.0f}, payouts {a['payouts']} | "
                         f"evals {a.get('evals_bought', 1)}, fees ${a.get('fees', 0):,.0f}, received ${a.get('paid', 0):,.0f}, net ${net:+,.0f}")
        return "\n".join(lines)
