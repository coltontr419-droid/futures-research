"""Catalog / registry consistency — an integrity test, per CLAUDE_FUTURES.md §7.

`hypotheses.yaml` is what the pipeline reads at Stage 0. `FUTURES_STRATEGY_HYPOTHESES.md`
is the human document. If they disagree, the pipeline silently tests something the catalog
does not describe, and every trial logged against that hypothesis is mislabelled — which
poisons the trial count N that DSR, PBO and SPA all depend on (§6).

That already happened once in the crypto project: an entry carried a horizon taken from its
prose header rather than its grid, expanding a hypothesis already at the parameter cap and
producing eighteen phantom trials silently. This test exists so that class of drift fails
loudly instead of being noticed by eye.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
REGISTRY: Final[Path] = ROOT / "hypotheses.yaml"
CATALOG: Final[Path] = ROOT / "FUTURES_STRATEGY_HYPOTHESES.md"

#: CLAUDE_FUTURES.md §5 Stage 5 — "Hard cap: 4 parameters. No exceptions."
HARD_PARAM_CAP: Final[int] = 4

REQUIRED_FIELDS: Final[frozenset[str]] = frozenset(
    {"id", "name", "mechanism", "condition", "horizon_minutes", "registered", "status"}
)

#: Closed set. A typo must not invent a category that later filters silently skip.
ALLOWED_STATUSES: Final[frozenset[str]] = frozenset({
    "untested", "stage1_inconclusive", "stage1_passed", "retired", "excluded", "dead",
})

#: Statuses that mean "will never be scheduled". Each needs a reason field.
RESOLVED_STATUSES: Final[frozenset[str]] = frozenset({
    "stage1_inconclusive", "stage1_passed", "retired", "excluded", "dead",
})

#: §5 Stage 4 needs two genuinely different instruments. MNQ and MGC are uncorrelated,
#: which is what makes the gate real here; ES/YM/RTY are ρ≈0.9 with NQ and are robustness
#: checks only, so they must never appear as a hypothesis's declared symbols.
STAGE4_INSTRUMENTS: Final[frozenset[str]] = frozenset({"MNQ", "MGC"})
ROBUSTNESS_ONLY: Final[frozenset[str]] = frozenset({"ES", "YM", "RTY", "NQ"})

REG: Final[dict[str, dict[str, Any]]] = {
    e["id"]: e for e in yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
}
CATALOG_TEXT: Final[str] = CATALOG.read_text(encoding="utf-8")


# ── schema ───────────────────────────────────────────────────────────────────


@pytest.mark.integrity
def test_every_entry_has_the_stage_0_schema() -> None:
    for hid, entry in REG.items():
        missing = REQUIRED_FIELDS - set(entry)
        assert not missing, f"{hid} is missing required fields {sorted(missing)}"


@pytest.mark.integrity
def test_ids_are_unique_and_well_formed() -> None:
    raw = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    ids = [e["id"] for e in raw]
    assert len(ids) == len(set(ids)), "duplicate id in the registry"
    assert all(re.fullmatch(r"F\d\d", i) for i in ids), ids


@pytest.mark.integrity
def test_statuses_are_from_the_closed_set() -> None:
    for hid, entry in REG.items():
        assert entry["status"] in ALLOWED_STATUSES, (
            f"{hid} has status {entry['status']!r}, not one of "
            f"{sorted(ALLOWED_STATUSES)}. A new status must be added deliberately, with "
            f"its own rules here — not introduced by a typo."
        )


@pytest.mark.integrity
def test_mechanism_names_a_counterparty_or_says_why_not() -> None:
    """§5 Stage 0: if the mechanism cannot be written plainly, the hypothesis is rejected.

    Three exemptions, and each carries its own obligation instead. A CONTROL exists to be
    failed and has no counterparty by design. A SCAN discovers which cell carries an effect
    rather than predicting it, so it has no counterparty yet. Both must say so in the
    mechanism text — the point is that the absence is declared, not tolerated. An EXCLUDED
    or DEAD entry is never tested at all, so the requirement does not bite; it must carry a
    reason instead, which a separate test enforces.
    """
    for hid, entry in REG.items():
        text = entry["mechanism"].lower()
        if entry["status"] in ("excluded", "dead"):
            # §5 Stage 0's requirement gates TESTING, and these are never tested. What they
            # must carry instead is a reason, checked by test_resolved_entries_carry_a_reason.
            # Demanding a counterparty story for an effect excluded on event count would be
            # asking for a mechanism nobody will ever use.
            continue
        if entry.get("is_control"):
            assert "not a hypothesis" in text, (
                f"{hid} is a control but its mechanism does not say so"
            )
            continue
        if entry.get("is_scan"):
            # A scan discovers which cell carries an effect rather than predicting it, so
            # it cannot name a counterparty yet. That is allowed ONLY if the entry says so
            # outright — the failure mode this guards against is inventing a mechanism
            # after the fact to fit whichever cell happened to win.
            assert "no counterparty is named" in text, (
                f"{hid} is a scan but does not state that it has no counterparty story. "
                f"An exploratory entry must say it is exploratory."
            )
            continue
        assert "counterparty" in text, (
            f"{hid}'s mechanism does not name a counterparty. §5 Stage 0 requires it: if "
            f"nobody is paying you, there is no edge to find."
        )


# ── the parameter cap ────────────────────────────────────────────────────────


@pytest.mark.integrity
def test_param_cap_is_within_the_hard_cap() -> None:
    for hid, entry in REG.items():
        cap = entry["param_cap"]
        assert 0 <= cap <= HARD_PARAM_CAP, (
            f"{hid} declares param_cap={cap}; §5 Stage 5 caps it at {HARD_PARAM_CAP}"
        )


@pytest.mark.integrity
def test_excluded_and_dead_entries_declare_no_parameters() -> None:
    for hid, entry in REG.items():
        if entry["status"] in ("excluded", "dead"):
            assert entry["param_cap"] == 0, (
                f"{hid} is {entry['status']} but declares {entry['param_cap']} parameters"
            )


# ── scheduling ───────────────────────────────────────────────────────────────


@pytest.mark.integrity
def test_only_untested_non_control_entries_have_a_test_order() -> None:
    for hid, entry in REG.items():
        order = entry.get("test_order")
        if entry["status"] == "untested" and not entry.get("is_control"):
            assert order is not None, f"{hid} is untested but has no test_order"
        else:
            assert order is None, (
                f"{hid} is {entry['status']}"
                f"{' (control)' if entry.get('is_control') else ''} but has "
                f"test_order={order} — nothing should schedule it"
            )


@pytest.mark.integrity
def test_test_order_has_no_ties_and_every_gap_is_explained() -> None:
    """Unique orders, and any gap must be a hypothesis that has since been resolved.

    The original rule demanded a contiguous 1..n permutation. Retiring an entry breaks that
    — F03 was order 2, and removing it leaves 1, 3, 4, ... The wrong fix is to renumber the
    survivors, because `test_order` records the priority set at REGISTRATION and rewriting
    it would erase that F03 was scheduled second and run second.

    So a resolved entry keeps its `registered_test_order` while its live `test_order` goes
    null, and a gap is legitimate exactly when some resolved entry claims it. A gap nobody
    claims is still a registration error and still fails.
    """
    live = [e["test_order"] for e in REG.values() if e.get("test_order") is not None]
    assert len(live) == len(set(live)), f"duplicate test_order: {sorted(live)}"
    assert all(o >= 1 for o in live), f"test_order must be >= 1, got {sorted(live)}"

    retired_orders = {e["registered_test_order"] for e in REG.values()
                      if e.get("registered_test_order") is not None}
    claimed = set(live) | retired_orders
    assert claimed == set(range(1, max(claimed) + 1)), (
        f"unexplained gap in test_order: live {sorted(live)}, "
        f"retired {sorted(retired_orders)}"
    )


@pytest.mark.integrity
def test_a_resolved_entry_that_had_an_order_records_it() -> None:
    """A hypothesis that was scheduled and then resolved must say where it sat.

    Without this, retiring an entry silently deletes the fact that it was ever prioritised,
    and the gap-explaining check above would have nothing to check against.
    """
    for hid, entry in REG.items():
        if entry["status"] == "retired":
            assert entry.get("registered_test_order") is not None, (
                f"{hid} is retired but does not record the test_order it was registered "
                f"with; the scheduling history is lost"
            )


@pytest.mark.integrity
def test_resolved_entries_carry_a_reason() -> None:
    """A status that closes a hypothesis must say what closed it."""
    field = {
        "retired": "retired_reason",
        "excluded": "excluded_reason",
        "stage1_inconclusive": "stage1_reason",
        "stage1_passed": "stage1_reason",
    }
    for hid, entry in REG.items():
        status = entry["status"]
        if status in field:
            assert entry.get(field[status]), (
                f"{hid} is {status} but gives no {field[status]}"
            )


# ── §5 Stage 4 ───────────────────────────────────────────────────────────────


@pytest.mark.integrity
def test_testable_entries_can_satisfy_stage_4() -> None:
    """Every schedulable hypothesis must declare both uncorrelated instruments.

    Stage 4 is a real gate here precisely because MNQ and MGC are uncorrelated — unlike
    BTC/ETH at ρ=0.835, where confirmation was nearly the same test twice. An entry
    declaring only one instrument could never pass it, and that should surface at
    registration rather than after the work is done.
    """
    for hid, entry in REG.items():
        if entry["status"] != "untested" or entry.get("is_control"):
            continue
        declared = {str(s).upper() for s in entry.get("symbols") or []}
        assert STAGE4_INSTRUMENTS <= declared, (
            f"{hid} declares symbols={sorted(declared)}; §5 Stage 4 needs both "
            f"{sorted(STAGE4_INSTRUMENTS)}"
        )


@pytest.mark.integrity
def test_no_entry_claims_a_correlated_instrument_as_evidence() -> None:
    """ES/YM/RTY/NQ are ρ≈0.9 with each other — robustness only, never Stage 4 evidence."""
    for hid, entry in REG.items():
        declared = {str(s).upper() for s in entry.get("symbols") or []}
        overlap = declared & ROBUSTNESS_ONLY
        assert not overlap, (
            f"{hid} declares {sorted(overlap)} in `symbols`. Those correlate ~0.9 with NQ "
            f"and are a robustness check, never Stage 4 evidence. Record them elsewhere."
        )


# ── the prop constraint ──────────────────────────────────────────────────────


@pytest.mark.integrity
def test_every_schedulable_hold_fits_inside_the_trading_day() -> None:
    """§2: flat by 17:00 ET, no exceptions.

    The longest declared hold must be short enough to terminate before the hard exit from
    any plausible entry in its session. 8 hours is the loosest bound that still catches a
    hypothesis whose hold is written in days — F12's 24-hour hold is exactly the case this
    is meant to catch, and it is excluded partly on that ground.
    """
    for hid, entry in REG.items():
        if entry["status"] != "untested":
            continue
        longest = max(entry["hold_hours"])
        assert longest <= 8, (
            f"{hid} declares a {longest}h hold, which cannot be guaranteed flat by "
            f"17:00 ET. §2 treats that as an invalid backtest, not an optimistic one."
        )


@pytest.mark.integrity
def test_horizons_are_consistent_with_declared_holds() -> None:
    for hid, entry in REG.items():
        hours = [m / 60 for m in entry["horizon_minutes"]]
        lo, hi = min(entry["hold_hours"]), max(entry["hold_hours"])
        assert min(hours) >= lo - 1e-9 and max(hours) <= hi + 1e-9, (
            f"{hid}: horizon_minutes {entry['horizon_minutes']} falls outside its declared "
            f"hold_hours {entry['hold_hours']}"
        )


# ── catalog agreement ────────────────────────────────────────────────────────


@pytest.mark.integrity
def test_every_registry_entry_appears_in_the_catalog() -> None:
    for hid in REG:
        assert re.search(rf"### {hid} — ", CATALOG_TEXT), (
            f"{hid} is in the registry but has no section in {CATALOG.name}"
        )


@pytest.mark.integrity
def test_every_catalog_entry_appears_in_the_registry() -> None:
    found = set(re.findall(r"^### (F\d\d) — ", CATALOG_TEXT, re.M))
    assert found == set(REG), (
        f"catalog and registry disagree: only in catalog {sorted(found - set(REG))}, "
        f"only in registry {sorted(set(REG) - found)}"
    )


@pytest.mark.integrity
def test_the_two_excluded_entries_are_the_expected_ones() -> None:
    """F12 and F13 are excluded by name in the catalog; assert the registry agrees.

    Pinned explicitly because "excluded" is the one status that costs zero trials, which
    makes it the cheapest place to hide a hypothesis someone did not want to test.
    """
    excluded = {h for h, e in REG.items() if e["status"] == "excluded"}
    assert excluded == {"F12", "F13"}, excluded
    assert "BELOW FIRING-RATE GATE" in CATALOG_TEXT
    assert "DECAYED" in CATALOG_TEXT


@pytest.mark.integrity
def test_the_two_controls_are_the_expected_ones() -> None:
    controls = {h for h, e in REG.items() if e.get("is_control")}
    assert controls == {"F10", "F11"}, controls
    for hid in controls:
        assert REG[hid]["grade"] == "D", f"{hid} is a control but is not graded D"


@pytest.mark.integrity
def test_f05_records_its_crypto_lineage() -> None:
    """F05 is a re-registration of crypto's S09, and the registry must say so.

    Without it, F05 looks like a fresh idea rather than a second look at a mechanism that
    already failed once on power and multiplicity — which is exactly the context needed to
    read its result honestly.
    """
    raw = REGISTRY.read_text(encoding="utf-8")
    block = raw[raw.index("- id: F05"):raw.index("- id: F06")]
    assert "S09" in block and "stage1_inconclusive" in block
    assert "do not transfer" in block, (
        "F05 must state that crypto's trials stay in the crypto project's N"
    )
