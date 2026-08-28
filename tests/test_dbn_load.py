"""Outright/spread classification and the canonical schema. CLAUDE_FUTURES.md §3.

The classification is the load-bearing part. A single calendar spread left in the series
would corrupt every volatility estimate downstream — a spread's price is a DIFFERENCE
between two contracts, typically near zero and free to change sign, so a percentage return
computed on it is meaningless. These tests pin the filter to `instrument_class` and prove
that a symbol-pattern shortcut would get it wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from futuresres.data.dbn_load import (
    CANONICAL,
    Instrument,
    classify,
    product_of,
    read_symbology,
    render_report,
    to_canonical,
)


def inst(iid: int, symbol: str, cls: str, legs: int = 0, product: str = "") -> Instrument:
    return Instrument(iid, symbol, cls, product or product_of(symbol), legs)


# ── product extraction ───────────────────────────────────────────────────────


@pytest.mark.integrity
@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("MNQZ5", "MNQ"), ("MNQH6", "MNQ"), ("MGCG6", "MGC"), ("MGCZ25", "MGC"),
        ("ESU5", "ES"), ("MNQZ5-MNQH6", "MNQ"),
    ],
)
def test_product_is_parsed_from_the_symbol(symbol: str, expected: str) -> None:
    assert product_of(symbol) == expected


@pytest.mark.integrity
def test_the_asset_field_wins_over_parsing_the_symbol() -> None:
    """The exchange states the product; deriving it from the symbol is a guess.

    This matters for any root whose last letter collides with a month code — parsing alone
    cannot tell a two-letter root followed by a month code from a three-letter root.
    """
    assert product_of("MNQZ5", asset="MNQ") == "MNQ"
    assert product_of("ANYTHING", asset="mgc") == "MGC"


# ── classification ───────────────────────────────────────────────────────────


@pytest.mark.integrity
def test_outrights_and_spreads_are_split_on_instrument_class() -> None:
    instruments = {
        1: inst(1, "MNQZ5", "F"),
        2: inst(2, "MNQH6", "F"),
        3: inst(3, "MNQZ5-MNQH6", "S", legs=2),
        4: inst(4, "MGCG6", "F"),
        5: inst(5, "MGCG6-MGCJ6", "S", legs=2),
    }
    cls = classify(instruments)
    assert set(cls.outrights) == {1, 2, 4}
    assert set(cls.spreads) == {3, 5}
    assert cls.disagreements == []


@pytest.mark.integrity
def test_options_and_option_spreads_are_not_kept() -> None:
    """Not requested in this batch, but assert rather than assume they would be excluded."""
    cls = classify({
        1: inst(1, "MNQZ5", "F"),
        2: inst(2, "MNQZ5 C20000", "C"),
        3: inst(3, "MNQZ5 P20000", "P"),
        4: inst(4, "SOMETHING", "T", legs=2),
        5: inst(5, "MIXED", "M", legs=2),
    })
    assert set(cls.outrights) == {1}
    assert set(cls.spreads) == {4, 5}
    assert set(cls.other) == {2, 3}


@pytest.mark.integrity
def test_a_symbol_pattern_would_get_this_wrong() -> None:
    """The reason the filter is on instrument_class and not on a hyphen in the symbol.

    Two failure directions, both real: a spread whose symbol carries no hyphen would be
    KEPT by a pattern test, and an outright whose symbol contains one would be DISCARDED.
    """
    instruments = {
        1: inst(1, "MNQ SPREAD 001", "S", legs=2),      # spread, no hyphen
        2: inst(2, "MNQ-SPECIAL", "F", legs=1),         # outright, has a hyphen
    }
    cls = classify(instruments)
    assert set(cls.spreads) == {1}, "a hyphen test would have kept this spread"
    assert set(cls.outrights) == {2}, "a hyphen test would have dropped this outright"


@pytest.mark.integrity
def test_leg_count_disagreeing_with_instrument_class_is_reported_not_resolved() -> None:
    """Two independent signals disagreeing means the data is not what we assume.

    Silently preferring one would be choosing which source to trust with no evidence, so
    the disagreement is surfaced and the instrument still lands somewhere deterministic.
    """
    cls = classify({1: inst(1, "WEIRD", "F", legs=3)})
    assert len(cls.disagreements) == 1
    assert "leg_count=3" in cls.disagreements[0]
    assert set(cls.spreads) == {1}, "multi-leg wins: it cannot be an outright"


@pytest.mark.integrity
def test_counts_by_product_separates_the_two_instruments() -> None:
    cls = classify({
        1: inst(1, "MNQZ5", "F"), 2: inst(2, "MNQH6", "F"),
        3: inst(3, "MNQZ5-MNQH6", "S", legs=2),
        4: inst(4, "MGCG6", "F"), 5: inst(5, "MGCJ6", "F"), 6: inst(6, "MGCM6", "F"),
    })
    counts = cls.counts_by_product()
    assert counts["MNQ"] == {"outright": 2, "spread": 1, "other": 0}
    assert counts["MGC"] == {"outright": 3, "spread": 0, "other": 0}


# ── canonical schema ─────────────────────────────────────────────────────────


def _bars() -> pl.DataFrame:
    return pl.DataFrame({
        "ts_event": pl.Series([1, 2, 3, 4], dtype=pl.Int64).cast(pl.Datetime("ns", "UTC")),
        "instrument_id": pl.Series([1, 1, 3, 4], dtype=pl.Int64),
        "open": [100.0, 101.0, 0.5, 2000.0],
        "high": [102.0, 103.0, 0.7, 2010.0],
        "low": [99.0, 100.0, 0.3, 1990.0],
        "close": [101.0, 102.0, 0.6, 2005.0],
        "volume": pl.Series([10, 20, 5, 30], dtype=pl.Int64),
    })


@pytest.mark.integrity
def test_canonical_drops_spread_bars_and_keeps_outrights() -> None:
    cls = classify({
        1: inst(1, "MNQZ5", "F"),
        3: inst(3, "MNQZ5-MNQH6", "S", legs=2),
        4: inst(4, "MGCG6", "F"),
    })
    out = to_canonical(_bars(), cls)
    assert out.height == 3, "the spread bar survived the filter"
    assert set(out.get_column("contract")) == {"MNQZ5", "MGCG6"}
    assert "MNQZ5-MNQH6" not in set(out.get_column("contract"))


@pytest.mark.integrity
def test_canonical_emits_exactly_the_declared_schema() -> None:
    cls = classify({1: inst(1, "MNQZ5", "F"), 3: inst(3, "S", "S", legs=2),
                    4: inst(4, "MGCG6", "F")})
    out = to_canonical(_bars(), cls)
    assert tuple(out.columns) == CANONICAL


@pytest.mark.integrity
def test_trades_is_null_because_ohlcv_does_not_carry_it() -> None:
    """Recorded as not-supplied rather than derived from volume — see the module docstring."""
    cls = classify({1: inst(1, "MNQZ5", "F"), 3: inst(3, "S", "S", legs=2),
                    4: inst(4, "MGCG6", "F")})
    out = to_canonical(_bars(), cls)
    assert out.get_column("trades").null_count() == out.height


@pytest.mark.integrity
def test_a_bar_referencing_an_unknown_instrument_raises() -> None:
    """Dropping it silently would hide a mismatched or incomplete extract."""
    cls = classify({1: inst(1, "MNQZ5", "F")})       # 3 and 4 are missing
    with pytest.raises(ValueError, match="absent from the definitions"):
        to_canonical(_bars(), cls)


@pytest.mark.integrity
def test_canonical_output_is_sorted_within_each_contract() -> None:
    cls = classify({1: inst(1, "MNQZ5", "F"), 3: inst(3, "S", "S", legs=2),
                    4: inst(4, "MGCG6", "F")})
    out = to_canonical(_bars(), cls)
    for (_, _), part in out.group_by(["symbol", "contract"]):
        ts = part.get_column("ts_event").to_list()
        assert ts == sorted(ts)


# ── symbology ────────────────────────────────────────────────────────────────


@pytest.mark.integrity
def test_symbology_maps_instrument_ids_to_symbols(tmp_path: Path) -> None:
    path = tmp_path / "symbology.json"
    path.write_text(json.dumps({"result": {
        "MNQZ5": [{"d0": "2026-01-01", "d1": "2026-03-20", "s": "42"}],
        "MGCG6": [{"d0": "2026-01-01", "d1": "2026-02-24", "s": "77"}],
    }}))
    assert read_symbology(path) == {42: "MNQZ5", 77: "MGCG6"}


@pytest.mark.integrity
def test_symbology_tolerates_an_unexpected_shape_without_inventing_entries(
    tmp_path: Path,
) -> None:
    path = tmp_path / "symbology.json"
    path.write_text(json.dumps({"result": "not a mapping"}))
    assert read_symbology(path) == {}


# ── the report ───────────────────────────────────────────────────────────────


@pytest.mark.integrity
def test_report_states_outrights_versus_spreads_per_product() -> None:
    cls = classify({
        1: inst(1, "MNQZ5", "F"), 2: inst(2, "MNQH6", "F"),
        3: inst(3, "MNQZ5-MNQH6", "S", legs=2),
        4: inst(4, "MGCG6", "F"),
    })
    text = render_report(cls)
    assert "| MNQ | 2 | 1 | 0 |" in text
    assert "| MGC | 1 | 0 | 0 |" in text
    assert "3 outrights kept" in text
    assert "1 spreads discarded" in text


@pytest.mark.integrity
def test_report_surfaces_disagreements_rather_than_hiding_them() -> None:
    cls = classify({1: inst(1, "WEIRD", "F", legs=4)})
    assert "disagree" in render_report(cls)
