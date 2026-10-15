"""A48 - forward record of the deployed dollar rules (decisions.md 463 review trigger, 578). No trial.

Pulls the bot's tickets.json from the droplet (read-only), and for every NKD dollar-week / FDXM DAX-dollar ticket replays its window on
Yahoo 1-minute bars (the bot's shadow.py; FDXM on the DAX index proxy) for the rule's side AND the opposite side, with the ticket's own
brackets. Window bars are cached under data/cache/forward/ (gitignored) because Yahoo keeps 1-minute history for ~30 days only - run at
least every few weeks. The §463 trigger: if the rules' signed window moves over the first 40 rule sessions sum negative, propose reverting.

    python -m futuresres.reporting.a48_forward [--no-pull]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "bot"))
import shadow  # noqa: E402
import schedule as sch  # noqa: E402

CACHE = ROOT / "data" / "cache" / "forward"
TICKETS = CACHE / "tickets.json"
OUT = ROOT / "reports" / "a48_forward.json"
RULE = {"NKD": "dollar-week", "FDXM": "DAX-dollar"}
TRIGGER_N = 40


def pull() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    subprocess.run(["scp", "-q", "futures-droplet:/opt/futures-bot/tickets.json", str(TICKETS)], check=True, timeout=60)


def window_bars(r: dict) -> list:
    f = CACHE / f"{r['product']}_{r['entry'][:16].replace(':', '')}.json"
    if f.exists():
        return [(dt.datetime.fromisoformat(t), o, h, l, c) for t, o, h, l, c in json.loads(f.read_text())]
    e, x = dt.datetime.fromisoformat(r["entry"]), dt.datetime.fromisoformat(r["exit"])
    if dt.datetime.now(x.tzinfo) < x + dt.timedelta(minutes=10):
        return []                                            # window not finished
    b = shadow.bars(r["product"], e, x)
    if b:
        f.write_text(json.dumps([(t.isoformat(), o, h, l, c) for t, o, h, l, c in b]))
    return b


def run(do_pull: bool = True) -> dict:
    if do_pull:
        pull()
    T = json.loads(TICKETS.read_text()); rows = []
    for r in T:
        tk = r.get("ticket") or {}
        if r["product"] not in RULE or not tk.get("trade") or RULE[r["product"]] not in (tk.get("note") or ""):
            continue
        b = window_bars(r)
        if not b:
            continue
        pp = sch.policy()["PRODUCTS"][r["product"]]; side = tk["side"]; other = "short" if side == "long" else "long"
        sim = lambda s: shadow.simulate(b, s, tk["take_points"], tk["stop_points"], tk["contracts"], pp["mult"], pp["rt"])
        a, o = sim(side), sim(other)
        move = (b[-1][4] / b[0][1] - 1) * 1e4 * (1 if side == "long" else -1)
        rows.append({"product": r["product"], "entry": r["entry"], "side": side, "signed_window_bps": round(move, 1),
                     "rule_side": a["outcome"], "rule_pnl": a.get("pnl"), "other_side": o["outcome"], "other_pnl": o.get("pnl"),
                     "recorded_pnl": r.get("user_pnl")})
    rows.sort(key=lambda x: x["entry"])
    first = rows[:TRIGGER_N]
    s = {"sessions": len(rows), "signed_bps_sum": round(sum(x["signed_window_bps"] for x in rows), 1),
         "rule_minus_other_pnl": round(sum((x["rule_pnl"] or 0) - (x["other_pnl"] or 0) for x in rows), 2),
         "recorded_pnl_sum": round(sum(x["recorded_pnl"] or 0 for x in rows), 2),
         "trigger": ("pending" if len(first) < TRIGGER_N else ("REVERT (first 40 negative)" if sum(x["signed_window_bps"] for x in first) < 0 else "keep")),
         "by_product": {p: {"sessions": sum(1 for x in rows if x["product"] == p),
                            "signed_bps_sum": round(sum(x["signed_window_bps"] for x in rows if x["product"] == p), 1),
                            "rule_minus_other_pnl": round(sum((x["rule_pnl"] or 0) - (x["other_pnl"] or 0) for x in rows if x["product"] == p), 2)}
                        for p in RULE}}
    OUT.write_text(json.dumps({"summary": s, "rows": rows}, indent=1) + "\n")
    for x in rows:
        print(f"{x['product']:4} {x['entry'][:16]} {x['side']:5} window {x['signed_window_bps']:+7.1f} bps | rule {x['rule_side']:9} {x['rule_pnl']:+8,.0f} "
              f"vs other side {x['other_side']:9} {x['other_pnl']:+8,.0f} | recorded {x['recorded_pnl'] if x['recorded_pnl'] is not None else '-'}")
    print(f"\n{s['sessions']} rule sessions: signed window {s['signed_bps_sum']:+.1f} bps; rule minus other side ${s['rule_minus_other_pnl']:+,.0f}; "
          f"recorded ${s['recorded_pnl_sum']:+,.0f}; trigger ({TRIGGER_N} sessions): {s['trigger']}")
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--no-pull", action="store_true")
    run(not ap.parse_args(argv).no_pull)
    return 0


if __name__ == "__main__":
    sys.exit(main())
