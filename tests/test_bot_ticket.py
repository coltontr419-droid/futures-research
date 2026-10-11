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
        product = ("MNQ", "MGC", "MCL")[rng.integers(3)]
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
