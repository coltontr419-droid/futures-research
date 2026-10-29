"""bot/fasttrack.py against the A123 engine's payout rule and the A124 100K terms (decisions.md §1144)."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bot"))

import fasttrack as ft  # noqa: E402
from futuresres.reporting.a122_fast_track_minute import TERMS  # noqa: E402
from futuresres.reporting.a124_fast_track_sizes import SIZES  # noqa: E402

T = dict(TERMS, **SIZES["100K"])


def test_terms_match_the_model():
    assert (ft.DD, ft.LOCK, ft.GOAL1, ft.GOALN, ft.PMIN, ft.SPLIT) == (T["dd"], T["lock"], T["goal1"], T["goalN"], T["pmin"], T["split"])
    assert ft.CAPS == T["caps"] and ft.CONS == T["cons"]


def test_brackets_are_800_and_4000():
    for s in ft.SLOTS.values():
        mult = 2.0 if s["symbol"] == "MNQ" else 10.0
        assert abs(s["qty"] * s["take"] * mult - 800) <= s["qty"] * mult * 0.25
        assert abs(s["qty"] * s["stop"] * mult - 4000) <= s["qty"] * mult * 0.25


def test_payout_matches_engine_rule():
    rng = random.Random(1144)
    for _ in range(5000):
        npay = rng.randint(0, 5); bal = ft.START + rng.uniform(-3000, 12000); cyc = rng.uniform(-2000, 10000); best = rng.uniform(0, 4000)
        goal = T["goal1"] if npay == 0 else T["goalN"]; cons = T["cons"][min(npay, 2)]
        amt = min(bal - ft.START - T["lock"], T["caps"][min(npay, 3)])
        engine = cyc >= goal and cyc > 0 and best <= cons * cyc and amt >= T["pmin"]
        assert ft.payout(bal, cyc, best, npay)["eligible"] == engine


def test_floor_locks_at_plus_100():
    assert ft.floor(0) == -4000 and ft.floor(3000) == -1000 and ft.floor(9000) == 100
    assert "skip" in ft.ticket("MNQ day", ft.START - 4000, ft.START)
