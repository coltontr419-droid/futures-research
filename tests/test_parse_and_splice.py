"""Parsing, decade resolution, splice convention and the DSR floor arithmetic.

The decade tests are the load-bearing ones. CME reuses single-digit year codes every ten
years, this batch spans sixteen, and `split_symbols` writes both contracts into one file —
so a symbol-keyed pipeline silently concatenates two contracts a decade apart. No OHLC,
duplicate or outlier check catches that, because every individual bar is valid. The
uniqueness assertion is what does, and it caught a real collision on the first run.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl
import pytest

from futuresres.data.parse import (
    assert_unique_contract_codes,
    classify_symbol,
    contract_code,
    resolve_contracts,
    resolve_expiry_year,
    ContractScan,
    SymbolForm,
)
from futuresres.data.splice import TICK, ConventionCheck, splice, verify_convention
from futuresres.reporting.kurtosis import dsr_min_events


# ── symbol grammar ───────────────────────────────────────────────────────────


@pytest.mark.integrity
@pytest.mark.parametrize(
    "symbol,kind,product",
    [("MGCG1", "outright", "MGC"), ("NQZ5", "outright", "NQ"),
     ("MNQH6", "outright", "MNQ"), ("MGCZ25", "outright", "MGC"),
     ("MGCG1-MGCJ1", "spread", "MGC"), ("NQZ5-NQH6", "spread", "NQ")],
)
def test_symbol_grammar(symbol: str, kind: str, product: str) -> None:
    form = classify_symbol(symbol)
    assert form.kind == kind and form.product == product


@pytest.mark.integrity
def test_a_hyphen_alone_does_not_make_a_spread() -> None:
    """Both legs must parse as outrights — this is the substring test's failure mode."""
    assert classify_symbol("MNQ-SPECIAL").kind == "unrecognised"
    assert classify_symbol("NOT A SYMBOL").kind == "unrecognised"


# ── the decade problem ───────────────────────────────────────────────────────


@pytest.mark.integrity
@pytest.mark.parametrize(
    "last_year,digit,expected",
    [
        (2011, 1, 2011),      # expired: last bar is in the expiry year
        (2021, 1, 2021),      # the same symbol, a decade later
        (2015, 5, 2015),
        (2025, 5, 2025),
        (2026, 8, 2028),      # not yet expired: data stops at the batch end
        (2025, 7, 2027),
        (2025, 9, 2029),
        (2024, 0, 2030),
    ],
)
def test_expiry_year_is_the_next_congruent_year_at_or_after_the_last_bar(
    last_year: int, digit: int, expected: int
) -> None:
    year, _ = resolve_expiry_year(last_year, digit)
    assert year == expected


@pytest.mark.integrity
def test_a_contract_never_resolves_to_an_expiry_before_its_last_bar() -> None:
    for last_year in range(2010, 2030):
        for digit in range(10):
            year, lead = resolve_expiry_year(last_year, digit)
            assert year >= last_year and 0 <= lead <= 9
            assert year % 10 == digit


@pytest.mark.integrity
def test_the_same_symbol_a_decade_apart_gets_two_different_codes() -> None:
    """The measured NQZ5 case: 2015 at ~4,000 points and 2025 at ~22,000."""
    frame = pl.DataFrame({
        "instrument_id": [12809] * 2 + [158704] * 2,
        "ts_event": [
            date(2014, 9, 22), date(2015, 12, 18),
            date(2024, 12, 27), date(2025, 12, 19),
        ],
    }).with_columns(pl.col("ts_event").cast(pl.Datetime("us", "UTC")))
    form = SymbolForm("NQZ5", "outright", product="NQ", month="Z", year_digit=5)
    contracts = resolve_contracts(frame, form)
    codes = {contract_code(c.product, c.month, c.expiry_year) for c in contracts}
    assert codes == {"NQZ2015", "NQZ2025"}


@pytest.mark.integrity
def test_two_contracts_resolving_to_the_same_code_is_an_error() -> None:
    """The collision that actually occurred: MGCG8 (Feb 2028) labelled MGCG2026."""
    a = ContractScan(1, "MGCG6", "MGC", "G", 2026, "2024-05-09", "2026-02-24", 126795, True)
    b = ContractScan(2, "MGCG8", "MGC", "G", 2026, "2026-04-08", "2026-08-27", 214, True)
    with pytest.raises(ValueError, match="collision"):
        assert_unique_contract_codes([a, b])


@pytest.mark.integrity
def test_distinct_codes_pass_the_uniqueness_check() -> None:
    a = ContractScan(1, "MGCG6", "MGC", "G", 2026, "", "", 1, True)
    b = ContractScan(2, "MGCG8", "MGC", "G", 2028, "", "", 1, True)
    assert_unique_contract_codes([a, b])


# ── splice convention ────────────────────────────────────────────────────────


def _series(ts: list[str], closes: list[float]) -> pl.DataFrame:
    return pl.DataFrame({
        "ts_event": pl.Series(ts).str.to_datetime("%Y-%m-%dT%H:%M:%S", time_zone="UTC"),
        "close": closes,
        "session": [date(2019, 5, 15)] * len(ts),
    })


@pytest.mark.integrity
def test_identical_conventions_pass_and_permit_the_splice() -> None:
    ts = [f"2019-05-15T14:{m:02d}:00" for m in range(10)]
    nq = _series(ts, [7000.0 + i * 0.25 for i in range(10)])
    mnq = _series(ts, [7000.0 + i * 0.25 for i in range(10)])
    check = verify_convention(nq, mnq, date(2019, 5, 1), date(2019, 5, 31))
    assert check.scale_free
    assert check.ratio_median == pytest.approx(1.0)
    assert check.abs_diff_max == 0.0


@pytest.mark.integrity
def test_a_tick_of_microstructure_still_passes() -> None:
    """Separate books do not print in lockstep; one tick is not a convention difference."""
    ts = [f"2019-05-15T14:{m:02d}:00" for m in range(20)]
    base = [7000.0 + i * 0.25 for i in range(20)]
    nq = _series(ts, base)
    mnq = _series(ts, [b + (TICK if i % 2 else 0.0) for i, b in enumerate(base)])
    check = verify_convention(nq, mnq, date(2019, 5, 1), date(2019, 5, 31))
    assert check.scale_free, "a one-tick residual was mistaken for a scaling factor"
    assert check.abs_diff_max == pytest.approx(TICK)


@pytest.mark.integrity
def test_a_tenfold_convention_difference_is_caught() -> None:
    """The failure this exists for: every return correct, every level wrong by 10x."""
    ts = [f"2019-05-15T14:{m:02d}:00" for m in range(10)]
    nq = _series(ts, [7000.0 + i for i in range(10)])
    mnq = _series(ts, [700.0 + i / 10 for i in range(10)])
    check = verify_convention(nq, mnq, date(2019, 5, 1), date(2019, 5, 31))
    assert not check.scale_free
    assert check.ratio_median == pytest.approx(0.1, abs=1e-3)


@pytest.mark.integrity
def test_splice_takes_nq_before_and_mnq_after() -> None:
    nq = pl.DataFrame({
        "ts_event": pl.Series(["2019-05-30T14:00:00", "2019-06-03T14:00:00"])
        .str.to_datetime("%Y-%m-%dT%H:%M:%S", time_zone="UTC"),
        "close": [7000.0, 7100.0], "session": [date(2019, 5, 30), date(2019, 6, 3)],
    })
    mnq = pl.DataFrame({
        "ts_event": pl.Series(["2019-05-30T14:00:00", "2019-06-03T14:00:00"])
        .str.to_datetime("%Y-%m-%dT%H:%M:%S", time_zone="UTC"),
        "close": [7000.5, 7100.5], "session": [date(2019, 5, 30), date(2019, 6, 3)],
    })
    out = splice(nq, mnq)
    rows = out.sort("ts_event").to_dicts()
    assert [r["source"] for r in rows] == ["NQ", "MNQ"]
    assert rows[0]["close"] == 7000.0 and rows[1]["close"] == 7100.5


# ── the DSR event floor ──────────────────────────────────────────────────────


@pytest.mark.integrity
def test_the_btc_46_event_wall_reproduces() -> None:
    """The crypto project's measured wall, from its measured 60m kurtosis."""
    assert dsr_min_events(66.9) == 46


@pytest.mark.integrity
def test_the_floor_is_linear_in_kurtosis() -> None:
    """n_min = 1 + (z/2)^2 (g4-1), so halving the excess kurtosis halves the floor."""
    a = dsr_min_events(101.0) - 1
    b = dsr_min_events(51.0) - 1
    assert a == pytest.approx(2 * b, rel=0.02)


@pytest.mark.integrity
def test_a_gaussian_tail_gives_the_smallest_possible_floor() -> None:
    """n_min = ceil(1 + (z/2)^2 (g4-1)); at the normal's g4 = 3 that is 3, not 2."""
    assert dsr_min_events(3.0) == 3
    assert dsr_min_events(1.5) == 2


@pytest.mark.integrity
def test_kurtosis_at_or_below_one_is_refused() -> None:
    with pytest.raises(ValueError):
        dsr_min_events(1.0)


@pytest.mark.integrity
def test_the_measured_futures_floors() -> None:
    """Pins the numbers reports/kurtosis.md quotes, so a formula change is visible."""
    assert dsr_min_events(115.1) == 79      # MNQ 1m
    assert dsr_min_events(226.5) == 154     # MGC 1m — fatter than BTC's 199.9
    assert dsr_min_events(25.9) == 18       # MNQ 60m
    assert dsr_min_events(199.9) == 136     # BTC 1m, for comparison
