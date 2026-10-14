"""The Discord bot's plain-Python ticket (bot/ticket.py, from bot/policy.json) must equal the playbook's
(futuresres.reporting.a06_playbook.ticket) on every state it can be asked about. decisions.md 123."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bot"))


@pytest.fixture(scope="module")
def both():
    import contextlib
    import io
    import ticket as bt
    import futuresres.reporting.a06_playbook as pb
    with contextlib.redirect_stdout(io.StringIO()):
        pb.export(ROOT / "bot" / "policy.json")
    bt._POLICY = None
    return bt, pb


def test_bot_ticket_matches_playbook(both):
    bt, pb = both
    rng = np.random.default_rng(123)
    for _ in range(3000):
        phase = "eval" if rng.random() < 0.6 else "funded"
        product = ("MNQ", "MGC", "MCL", "NKD", "FDXM", "ZS")[rng.integers(6)]
        peak = 50_000 + float(rng.integers(0, 4_200))
        balance = float(np.round(peak - rng.uniform(0, 2_100), 2))
        best = float(rng.uniform(0, 1_900)) if phase == "eval" else 0.0
        payouts = int(rng.integers(0, 5))
        a = pb.ticket(phase, balance, peak, best, payouts, None, product)
        b = bt.ticket(phase, balance, peak, best, payouts, product)
        assert a.get("trade") == b.get("trade") and a.get("finished") == b.get("finished"), (phase, balance, peak, best, payouts, product)
        if a["trade"]:
            for k in ("take_net", "stop_net", "floor", "take_points", "stop_points", "contracts"):
                assert a[k] == pytest.approx(b[k]), (k, phase, balance, peak, best, payouts, product, a, b)


def test_book_rules(tmp_path):
    import accounts as ac
    bk = ac.Book(tmp_path / "s.json", tmp_path / "log.csv")
    assert bk.floor(bk.s["MNQ"]) == 48_000
    bk.eod("MNQ", 51_200); bk.eod("MNQ", 52_400)
    msgs = bk.eod("MNQ", 53_000)                     # profit 3,000, best day 1,200 <= 40% of 3,000 -> pass
    assert any("PASSED" in m for m in msgs) and bk.s["MNQ"]["phase"] == "funded"
    bk.eod("MNQ", 52_100); msgs = bk.eod("MNQ", 52_700)
    assert any("payout of $700.00" in m for m in msgs)
    bk.payout("MNQ", 700); assert bk.s["MNQ"]["balance"] == 52_000 and bk.s["MNQ"]["payouts"] == 1
    assert any("FAILED" in m for m in bk.eod("MGC", 47_990)) and bk.s["MGC"]["phase"] == "dead"
    bk.new("MGC"); assert bk.s["MGC"]["phase"] == "eval" and bk.s["MGC"]["evals_bought"] == 2
    assert (tmp_path / "log.csv").read_text().count("\n") >= 8


def test_schedule_alert_track_and_report(tmp_path):
    import datetime as dt
    import accounts as ac
    import schedule as sc
    bk = ac.Book(tmp_path / "s.json", tmp_path / "log.csv")
    tx = sc.Tickets(tmp_path / "t.json", tmp_path / "shadow.csv")
    sun = dt.datetime(2026, 10, 11, 17, 30, tzinfo=sc.ET)                    # a Sunday
    text = sc.alert_text(bk, tx, sun)
    assert text.count("BUY") == 6
    win = {r["product"]: (r["entry"], r["exit"]) for r in tx.t}
    assert win["MCL"] == ("2026-10-11T18:00:00-04:00", "2026-10-12T16:55:00-04:00")
    assert win["MGC"] == ("2026-10-12T03:00:00-04:00", "2026-10-12T11:30:00-04:00")
    assert win["MNQ"] == ("2026-10-12T09:30:00-04:00", "2026-10-12T16:00:00-04:00")
    assert win["NKD"] == ("2026-10-11T20:00:00-04:00", "2026-10-12T02:00:00-04:00")      # 09:00-15:00 Tokyo
    assert win["FDXM"] == ("2026-10-12T03:00:00-04:00", "2026-10-12T11:30:00-04:00")     # 09:00-17:30 Frankfurt
    assert win["ZS"] == ("2026-10-11T20:00:00-04:00", "2026-10-12T14:15:00-04:00")       # 19:00-13:15 Chicago
    # shadow-track with a fake feed: price rises straight through the take
    def fetch(product, start, end):
        t, out, px = start, [], 100.0
        while t < end:
            out.append((t, px, px + 50.0, px - 0.001, px + 50.0)); px += 50.0; t += dt.timedelta(minutes=1)
        return out
    done = tx.track(dt.datetime(2026, 10, 12, 17, 10, tzinfo=sc.ET), fetch=fetch)
    assert {r["product"] for r in done} == {"MCL", "MGC", "MNQ", "NKD", "FDXM", "ZS"} and all(r["result"]["outcome"] == "TAKE" for r in done)
    assert (tmp_path / "shadow.csv").read_text().count("TAKE") == 6
    mon = dt.datetime(2026, 10, 12, 17, 30, tzinfo=sc.ET)
    for p, b in (("MNQ", 51_000), ("MGC", 50_500), ("MCL", 49_500), ("NKD", 50_200), ("FDXM", 50_900), ("ZS", 50_100)):
        bk.eod(p, b, "2026-10-12")
    text = sc.alert_text(bk, tx, mon)
    assert "Results" in text and text.count("TAKE") == 6 and "not recorded" not in text
    assert "Results" not in sc.alert_text(bk, tx, mon)                     # each result reported once
    fri = dt.datetime(2026, 10, 16, 17, 30, tzinfo=sc.ET)
    fri_text = sc.alert_text(bk, tx, fri)
    assert "No new tickets" in fri_text and "Weekly check" in fri_text and "take / stop / time exit **6 / 0 / 0**" in fri_text
    assert "ticks" in sc.ticket_post(tx.t[-1]) or tx.t[-1]["status"] == "done"


def test_existing_three_account_state_gains_the_new_accounts(tmp_path):
    import json
    import accounts as ac
    old = {p: ac.fresh(p) for p in ("MNQ", "MGC", "MCL")}
    old["MNQ"]["balance"] = 51_234.0
    (tmp_path / "s.json").write_text(json.dumps(old))
    bk = ac.Book(tmp_path / "s.json", tmp_path / "log.csv")
    assert bk.s["MNQ"]["balance"] == 51_234.0 and bk.s["NKD"]["phase"] == "eval" and bk.s["FDXM"]["balance"] == 50_000.0 and bk.s["ZS"]["phase"] == "eval"


def test_eod_is_filed_under_the_ending_tickets_trading_day(tmp_path):
    """`!eod` sent as soon as a bracket resolves (02:48 for crude, 11:21 for Nikkei, 16:24 for MNQ) belongs to the trading
    day of the ticket that just ended - the date the next 17:30 alert checks - not the clock's previous trading day."""
    import datetime as dt
    import accounts as ac
    import schedule as sc
    bk = ac.Book(tmp_path / "s.json", tmp_path / "log.csv")
    tx = sc.Tickets(tmp_path / "t.json", tmp_path / "shadow.csv")
    sc.alert_text(bk, tx, dt.datetime(2026, 10, 12, 17, 30, tzinfo=sc.ET))                    # Monday's alert
    for p, when in (("MCL", (10, 13, 2, 48)), ("NKD", (10, 13, 1, 15)), ("MGC", (10, 13, 11, 22)), ("MNQ", (10, 13, 16, 24)),
                    ("ZS", (10, 13, 3, 50)), ("FDXM", (10, 13, 9, 40))):
        now = dt.datetime(2026, *when, tzinfo=sc.ET)
        assert sc.eod_day(tx, p, now) == "2026-10-13", (p, sc.eod_day(tx, p, now))
        bk.eod(p, 50_000.0, sc.eod_day(tx, p, now))
    text = sc.alert_text(bk, tx, dt.datetime(2026, 10, 13, 17, 30, tzinfo=sc.ET))
    assert "not recorded" not in text
    # before any ticket has started: the clock rule
    tx2 = sc.Tickets(tmp_path / "t2.json", tmp_path / "s2.csv")
    assert sc.eod_day(tx2, "MNQ", dt.datetime(2026, 10, 13, 16, 0, tzinfo=sc.ET)) == "2026-10-12"


def test_d139_nkd_side_fades_a_bitcoin_shock() -> None:
    """D139 (decisions.md 432): NKD fades a BTC=F session beyond 2 sigma; otherwise, or without data, long."""
    import datetime as _dt
    import d139
    base = [(_dt.date(2026, 1, 1) + _dt.timedelta(days=i), 100.0 * (1 if i % 2 else -1)) for i in range(60)]
    day = _dt.date(2026, 3, 2)
    assert d139.nkd_side(day, base + [(day, 500.0)])[0] == "short"
    assert d139.nkd_side(day, base + [(day, -500.0)])[0] == "long"
    assert d139.nkd_side(day, base + [(day, 50.0)])[0] == "long"
    assert d139.nkd_side(day, [])[0] == "long"
