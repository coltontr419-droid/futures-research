"""What the bot posts, and when - plain Python, testable without Discord. decisions.md 125.

One alert a day at 17:30 New York time (the user's schedule), after the 17:00 close:
  Sun-Thu: how the finished tickets played out (shadow results) + any missing closing balances + the next tickets -
           crude (MCL) entering 18:00 tonight, gold (MGC) 03:00 tomorrow, Nasdaq (MNQ) 09:30 tomorrow.
  Fri:     results only (no session until Sunday evening).
Every ticket is recorded and, once its window has closed, shadow-tracked on free Yahoo 1-minute bars (shadow.py),
whether or not it was traded; `!took` / `!skipped` mark which.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import shadow
from accounts import PRODUCTS, Book
from ticket import describe, policy, ticket

ET = ZoneInfo("America/New_York")
ALERT = (17, 30)
#: product -> (time zone, entry day offset from the alert's New York date, entry hh:mm, exit day offset, exit hh:mm), local time.
#: NKD and FDXM (decisions.md 138) follow Tokyo and Frankfurt clocks, so their New York times shift with daylight saving.
WINDOWS = {"MCL": (ET, 0, (18, 0), 1, (16, 55)), "MGC": (ET, 1, (3, 0), 1, (11, 30)), "MNQ": (ET, 1, (9, 30), 1, (16, 0)),
           "NKD": (ZoneInfo("Asia/Tokyo"), 1, (9, 0), 1, (15, 0)), "FDXM": (ZoneInfo("Europe/Berlin"), 1, (9, 0), 1, (17, 30))}
ORDER = ("MCL", "NKD", "MGC", "FDXM", "MNQ")         # by entry time after the 17:30 alert
SHADOW_DELAY = dt.timedelta(minutes=5)


def last_trading_day(d: dt.date) -> dt.date:
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


class Tickets:
    def __init__(self, path: Path, log_path: Path):
        self.path, self.log_path = Path(path), Path(log_path)
        self.t: list[dict] = json.loads(self.path.read_text()) if self.path.exists() else []

    def save(self) -> None:
        self.t = self.t[-500:]
        tmp = self.path.with_suffix(".tmp"); tmp.write_text(json.dumps(self.t, indent=1)); tmp.replace(self.path)

    def issue(self, book: Book, product: str, alert_day: dt.date, now: dt.datetime) -> dict | None:
        """Record (or replace, if still pending) the ticket for `product` from the alert on `alert_day`."""
        a = book.s[product]
        tz, e_off, (eh, em), x_off, (xh, xm) = WINDOWS[product]
        entry = dt.datetime.combine(alert_day + dt.timedelta(days=e_off), dt.time(eh, em), tz).astimezone(ET)
        exit_ = dt.datetime.combine(alert_day + dt.timedelta(days=x_off), dt.time(xh, xm), tz).astimezone(ET)
        if a["phase"] == "dead":
            tk = {"trade": False, "finished": True, "floor": 0.0}
        else:
            tk = ticket(a["phase"], a["balance"], a["peak"], a["best"], a["payouts"], product)
        rec = {"product": product, "issued": now.isoformat(timespec="seconds"), "entry": entry.isoformat(), "exit": exit_.isoformat(),
               "phase": a["phase"], "balance": a["balance"], "ticket": tk, "status": "pending" if tk.get("trade") else "none",
               "traded": None, "result": None}
        self.t = [r for r in self.t if not (r["product"] == product and r["entry"] == rec["entry"] and r["status"] in ("pending", "none"))]
        self.t.append(rec); self.save()
        return rec

    def pending_due(self, now: dt.datetime) -> list[dict]:
        return [r for r in self.t if r["status"] == "pending" and dt.datetime.fromisoformat(r["exit"]) + SHADOW_DELAY <= now]

    def track(self, now: dt.datetime, fetch=shadow.bars) -> list[dict]:
        """Shadow-track every ticket whose window has closed; returns the newly finished records."""
        done = []
        for r in self.pending_due(now):
            tk = r["ticket"]; p = policy()["PRODUCTS"][r["product"]]
            try:
                b = fetch(r["product"], dt.datetime.fromisoformat(r["entry"]), dt.datetime.fromisoformat(r["exit"]))
            except Exception as e:                         # Yahoo down: try again next pass
                r["last_error"] = f"{type(e).__name__}: {e}"; continue
            res = shadow.simulate(b, tk["side"], tk["take_points"], tk["stop_points"], tk["contracts"], p["mult"], p["rt"])
            if res["outcome"] == "NO DATA" and now - dt.datetime.fromisoformat(r["exit"]) < dt.timedelta(days=2):
                continue
            r["result"] = res; r["status"] = "done"; done.append(r); self._log(r)
        if done:
            self.save()
        return done

    def mark(self, product: str, traded: bool) -> dict | None:
        cands = [r for r in self.t if r["product"] == product and r["status"] in ("pending", "done") and r["traded"] is None]
        if not cands:
            return None
        r = cands[-1]; r["traded"] = traded; self.save()
        return r

    def _log(self, r: dict) -> None:
        new = not self.log_path.exists()
        tk, res = r["ticket"], r["result"]
        row = {"entry": r["entry"], "exit": r["exit"], "product": r["product"], "phase": r["phase"], "balance": r["balance"],
               "side": tk["side"], "contracts": tk["contracts"], "take_pts": tk["take_points"], "stop_pts": tk["stop_points"],
               "take_net": tk["take_net"], "stop_net": tk["stop_net"], "outcome": res["outcome"], "outcome_time": res.get("time", ""),
               "entry_px": res.get("entry", ""), "exit_px": res.get("exit", ""), "pnl": res.get("pnl", ""),
               "traded": "" if r["traded"] is None else ("yes" if r["traded"] else "no")}
        with self.log_path.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row)); new and w.writeheader(); w.writerow(row)

    def unreported(self) -> list[dict]:
        out = [r for r in self.t if r["status"] == "done" and not r.get("reported")]
        for r in out:
            r["reported"] = True
        if out:
            self.save()
        return out

    def summary(self, last: int = 0) -> str:
        done = [r for r in self.t if r["status"] == "done"]
        if last:
            done = done[-last:]
        if not done:
            return "No finished tickets yet."
        lines = [result_line(r) for r in done]
        tot = sum((r["result"].get("pnl") or 0) for r in done)
        n = {k: sum(1 for r in done if r["result"]["outcome"] == k) for k in ("TAKE", "STOP", "TIME EXIT")}
        lines.append(f"**{len(done)} tickets: {n['TAKE']} take, {n['STOP']} stop, {n['TIME EXIT']} time exit; total ${tot:+,.0f}**")
        return "\n".join(lines)


def result_line(r: dict) -> str:
    res = r["result"]; e = dt.datetime.fromisoformat(r["entry"])
    tr = {None: "", True: " (traded)", False: " (skipped)"}[r["traded"]]
    if res["outcome"] == "NO DATA":
        return f"{r['product']} {e:%a %d %b %H:%M}: no price data{tr}"
    return (f"{r['product']} {e:%a %d %b %H:%M}: **{res['outcome']}** at {res['time']} -> ${res['pnl']:+,.0f} "
            f"(entry {res['entry']:.2f}){tr}")


def alert_text(book: Book, tix: Tickets, now: dt.datetime) -> str:
    """The 17:30 post. Issues and records the next tickets (Sun-Thu)."""
    parts = []
    res = tix.unreported()
    if res:
        parts.append("**Results** (shadow-tracked; how each ticket played out):\n" + "\n".join(result_line(r) for r in res))
    want = last_trading_day(now.date())
    missing = [p for p in PRODUCTS if book.s[p].get("eod_date") != want.isoformat() and book.s[p]["phase"] != "dead"]
    if now.weekday() in (6, 0, 1, 2, 3):          # Sun-Thu: a session follows
        if missing:
            parts.append("Closing balance not recorded for " + ", ".join(missing) + f" ({want:%a %d %b}) - tickets below use the "
                         "last recorded balance. Send `!eod <PRODUCT> <balance>` and I'll reissue that ticket.")
        for p in ORDER:
            rec = tix.issue(book, p, now.date(), now)
            parts.append(ticket_post(rec))
    else:
        if missing:
            parts.append("Closing balance not recorded for " + ", ".join(missing) + ". Send `!eod <PRODUCT> <balance>`.")
        parts.append("No new tickets - next session opens Sunday 18:00 ET; tickets at Sunday 17:30.")
    return "\n\n".join(parts) if parts else "Nothing to report."


def ticket_post(rec: dict) -> str:
    e = dt.datetime.fromisoformat(rec["entry"]); x = dt.datetime.fromisoformat(rec["exit"])
    head = f"__{rec['product']} - {e:%a %d %b} {e:%H:%M} -> {x:%a} {x:%H:%M} ET__ [{rec['phase']}, balance ${rec['balance']:,.2f}]"
    if rec["phase"] == "dead":
        return head + f"\n**{rec['product']}: account failed** - buy a new evaluation and send `!new {rec['product']}`."
    return head + "\n" + describe(rec["ticket"], rec["product"])
