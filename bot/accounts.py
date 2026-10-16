"""Account bookkeeping for the demo: Tradeify Select Daily rules as the programme models them (decisions.md 81-82,
user's terms). One account per product; state in a JSON file; every event appended to a CSV demo log.
Plain Python; no Discord here, so it is testable on its own. decisions.md 123.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
from pathlib import Path

START, TARGET, TRAIL, LOCK_AT, CONSISTENCY, CAP, LIVE_AFTER, FEE = 50_000.0, 3_000.0, 2_000.0, 52_000.0, 0.40, 1_250.0, 3, 80.0
# Tradeify live (decisions.md 623, 640): moved at 3 payouts on one account or 10 on the book; accounts holding a payout go live, the rest
# close; live = $0 start, $2,000 trailing drawdown locking at $0, withdrawals above it at 80%; no new evaluations while one is live;
# up to 4 weeks' cool-off after the last live account ends.
LIVE_DD, LIVE_SPLIT, BOOK_LIVE_AT, COOL_DAYS = 2_000.0, 0.80, 10, 28
CLOSED = ("dead", "closed")
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
DEFAULT_ACCOUNTS = ("MNQ", "MGC", "MCL", "NKD", "FDXM", "ZS")    # NKD, FDXM: accounts 4-5 (decisions.md 138); ZS: demo-only sixth (141)


def _accounts() -> tuple:
    """The accounts the bot runs: BOT_ACCOUNTS (environment, or the .env beside this file), e.g. "NKD,NKD2,NKD3,FDXM,FDXM2" for the
    live plan (decisions.md 635) - an account is its product's name plus an optional number. Default: the demo's six products."""
    v = os.environ.get("BOT_ACCOUNTS", "")
    if not v:
        env = Path(__file__).with_name(".env")
        if env.exists():
            for line in env.read_text().splitlines():
                if line.strip().startswith("BOT_ACCOUNTS="):
                    v = line.split("=", 1)[1].strip()
    acc = tuple(x.strip().upper() for x in v.split(",") if x.strip())
    return acc or DEFAULT_ACCOUNTS


def base(account: str) -> str:
    """The traded product of an account name: "NKD2" -> "NKD", "FDXM" -> "FDXM"."""
    return re.sub(r"\d+$", "", account.upper())


PRODUCTS = _accounts()


def fresh(product: str) -> dict:
    return {"product": product, "phase": "eval", "balance": START, "peak": START, "best": 0.0, "payouts": 0,
            "evals_bought": 1, "fees": FEE, "paid": 0.0, "since": dt.datetime.now(ET).date().isoformat(),
            "eod_date": dt.datetime.now(ET).date().isoformat()}


class Book:
    def __init__(self, state_path: Path, log_path: Path):
        self.state_path, self.log_path = Path(state_path), Path(log_path)
        self.s = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        for p in PRODUCTS:                         # products added later start as fresh evaluations
            self.s.setdefault(p, fresh(p))
        self.s.setdefault("_book", {"payouts": 0, "mode": "sim", "cool_until": None, "alerted": False})

    @property
    def bk(self) -> dict:
        return self.s["_book"]

    # ------------------------------------------------------------------ persistence
    def save(self) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.s, indent=1)); tmp.replace(self.state_path)

    def log(self, product: str, event: str, **kw) -> None:
        new = not self.log_path.exists()
        a = self.s[product]
        # New York time with its offset (the droplet runs on UTC; rows before 2026-10-13 are naive UTC)
        row = {"time": dt.datetime.now(ET).isoformat(timespec="seconds"), "product": product, "event": event,
               "phase": a["phase"], "balance": a["balance"], "peak": a["peak"], "best_day": a["best"],
               "payouts": a["payouts"], **{k: kw.get(k, "") for k in ("amount", "pnl", "note")}}
        with self.log_path.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row)); new and w.writeheader(); w.writerow(row)

    # ------------------------------------------------------------------ rules
    @staticmethod
    def floor(a: dict) -> float:
        if a["phase"] == "live":
            return 0.0 if a["peak"] >= LIVE_DD else a["peak"] - LIVE_DD
        if a["phase"] == "eval":
            return a["peak"] - TRAIL                        # trails the EOD peak, never locks
        return START if a["peak"] >= LOCK_AT else a["peak"] - TRAIL

    def eod(self, product: str, balance: float, day: str | None = None) -> list[str]:
        """Record an end-of-day balance (for trading day `day`, ISO date); returns the messages to post."""
        a = self.s[product]; msgs = []
        a["eod_date"] = day or dt.datetime.now(ET).date().isoformat()
        fl = self.floor(a)
        pnl = balance - a["balance"]
        a["balance"] = balance
        if balance <= fl:
            self.log(product, "EOD", pnl=pnl, note="breached floor")
            if a["phase"] == "live":
                a["phase"] = "closed"
                msgs.append(f"**{product} LIVE ACCOUNT ENDED** - closed ${balance:,.2f} at or below its floor ${fl:,.0f}.")
                msgs += self._live_check(day)
                self.save(); return msgs
            msgs.append(f"**{product} {a['phase']} FAILED** - closed ${balance:,.2f} at or below the floor ${fl:,.0f}. "
                        f"Buy a new evaluation and send `!new {product}`.")
            a["phase"] = "dead"; self.save(); return msgs
        a["peak"] = max(a["peak"], balance)
        if a["phase"] == "live":
            self.log(product, "EOD", pnl=pnl)
            amt = max(balance - LIVE_DD, 0.0) if a["peak"] >= LIVE_DD else 0.0
            if amt > 0:
                msgs.append(f"**{product} (live): request a withdrawal of ${amt:,.2f}** (you keep 80%: ${LIVE_SPLIT * amt:,.2f}). "
                            f"When paid, send `!payout {product} {amt:.2f}`.")
        elif a["phase"] == "eval":
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
        if a["phase"] == "live":
            a["balance"] -= amount; a["paid"] += LIVE_SPLIT * amount; a["live_paid"] = a.get("live_paid", 0.0) + LIVE_SPLIT * amount
            self.log(product, "LIVE_PAYOUT", amount=amount); self.save()
            return (f"{product} (live): withdrawal ${amount:,.2f} recorded (you received ${LIVE_SPLIT * amount:,.2f}). "
                    f"Balance ${a['balance']:,.2f}.")
        a["balance"] -= amount; a["payouts"] += 1; a["paid"] += 0.9 * amount
        self.bk["payouts"] = self.bk.get("payouts", 0) + 1
        self.log(product, "PAYOUT", amount=amount); self.save()
        msg = f"{product}: payout ${amount:,.2f} recorded (#{a['payouts']}; you received ${0.9 * amount:,.2f}). Balance ${a['balance']:,.2f}."
        trig = self.live_trigger()
        if trig and not self.bk.get("alerted"):
            self.bk["alerted"] = True; self.save()
            return msg + "\n\n" + trig
        return msg

    # ------------------------------------------------------------------ the move to live (decisions.md 623, 640, 653, 657)
    def live_trigger(self) -> str:
        """The move-to-live notice, if the book has just met Tradeify's trigger; '' otherwise."""
        if self.bk.get("mode") != "sim":
            return ""
        three = [p for p in PRODUCTS if self.s[p]["phase"] == "funded" and self.s[p]["payouts"] >= LIVE_AFTER]
        if not three and self.bk.get("payouts", 0) < BOOK_LIVE_AT:
            return ""
        go = [p for p in PRODUCTS if self.s[p]["phase"] == "funded" and self.s[p]["payouts"] >= 1]
        shut = [p for p in PRODUCTS if p not in go]
        why = f"{three[0]} has {LIVE_AFTER} payouts" if three else f"the book has {self.bk['payouts']} payouts"
        return (f"**MOVE TO LIVE expected** ({why}). Tradeify should move these accounts to live: **{', '.join(go)}**; "
                f"these close: {', '.join(shut) or 'none'}. Live accounts start at $0 with a $2,000 drawdown and trade larger "
                f"(3 NKD / 4 FDXM). When Tradeify confirms, send `!golive` (or `!golive NKD FDXM2 ...` to name the live accounts yourself).")

    def golive(self, names: list[str] | None = None, day: str | None = None) -> str:
        go = names or [p for p in PRODUCTS if self.s[p]["phase"] == "funded" and self.s[p]["payouts"] >= 1]
        if not go:
            return "No account holds a payout - nothing can go live."
        for p in PRODUCTS:
            a = self.s[p]
            if p in go:
                a.update(phase="live", balance=0.0, peak=0.0, best=0.0, live_since=day or dt.datetime.now(ET).date().isoformat())
                self.log(p, "LIVE")
            elif a["phase"] not in CLOSED:
                a["phase"] = "closed"; self.log(p, "CLOSED", note="moved to live")
            else:
                a["phase"] = "closed"
        self.bk.update(mode="live", alerted=True); self.save()
        return (f"**Live: {', '.join(go)}** - each starts at $0 (floor -$2,000 until it reaches +$2,000, then $0). Other accounts are "
                f"closed; no new evaluations while a live account is open. Tickets now use the live plan (3 NKD / 4 FDXM). "
                f"After each window: `!eod <ACCOUNT> <balance>` with the live balance (e.g. `!eod NKD 850`).")

    def _live_check(self, day: str | None) -> list[str]:
        """After a live account ends: if none is left, the cool-off starts."""
        if any(self.s[p]["phase"] == "live" for p in PRODUCTS):
            return []
        d = dt.date.fromisoformat(day) if day else dt.datetime.now(ET).date()
        until = (d + dt.timedelta(days=COOL_DAYS)).isoformat()
        self.bk.update(mode="cool", cool_until=until, payouts=0, alerted=False)
        return [f"**No live account left - cool-off.** Tradeify allows new evaluations again after up to 4 weeks (by {until} at the "
                f"latest; check your dashboard). Then buy evaluations and send `!new <ACCOUNT>` for each."]

    def can_buy(self) -> str:
        """'' if a new evaluation may be bought now; otherwise why not."""
        if any(self.s[p]["phase"] == "live" for p in PRODUCTS):
            return "A live account is open - Tradeify allows no new evaluations until it ends."
        cu = self.bk.get("cool_until")
        if self.bk.get("mode") == "cool" and cu and dt.datetime.now(ET).date().isoformat() < cu:
            return f"In cool-off until up to {cu} - check Tradeify's dashboard; if it already allows new evaluations, resend with `confirm`."
        return ""

    def new(self, product: str) -> str:
        if self.bk.get("mode") in ("cool", "live") and not any(self.s[p]["phase"] == "live" for p in PRODUCTS):
            self.bk.update(mode="sim", payouts=0, alerted=False)                 # the cycle restarts with the first new evaluation
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
        b = self.bk
        lines = [f"Book: {b.get('mode', 'sim')}" + (f", payouts toward live {b.get('payouts', 0)}/{BOOK_LIVE_AT}" if b.get("mode") == "sim" else "")
                 + (f", cool-off until up to {b['cool_until']}" if b.get("mode") == "cool" else "")]
        for p in PRODUCTS:
            a = self.s[p]
            net = a.get("paid", 0.0) - a.get("fees", 0.0)
            lines.append(f"**{p}** {a['phase']}: balance ${a['balance']:,.2f}, peak ${a['peak']:,.2f}, floor "
                         f"${self.floor(a) if a['phase'] not in CLOSED else 0:,.0f}, best day ${a['best']:,.0f}, payouts {a['payouts']} | "
                         f"evals {a.get('evals_bought', 1)}, fees ${a.get('fees', 0):,.0f}, received ${a.get('paid', 0):,.0f}, net ${net:+,.0f}")
        return "\n".join(lines)
