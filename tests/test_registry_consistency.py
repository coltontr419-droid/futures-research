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
LEVEL_CATALOG: Final[Path] = ROOT / "LEVEL_HYPOTHESES.md"

#: CLAUDE_FUTURES.md §5 Stage 5 — "Hard cap: 4 parameters. No exceptions."
HARD_PARAM_CAP: Final[int] = 4

REQUIRED_FIELDS: Final[frozenset[str]] = frozenset(
    {"id", "name", "mechanism", "condition", "horizon_minutes", "registered", "status"}
)

#: Closed set. A typo must not invent a category that later filters silently skip.
#:
#: `stage1_inconclusive` vs `stage1_uninformative` is a real distinction, not a synonym.
#: INCONCLUSIVE means the test ran with adequate power and the reading did not resolve —
#: S09 in the crypto catalog: nominal hits above chance, none surviving BH, mechanism
#: uncontradicted. UNINFORMATIVE means the test could not have produced evidence at all,
#: because the sample sits below the range where a detection floor was ever resolved. The
#: first is a result; the second is the absence of one, and collapsing them would let an
#: unpowered null read as a considered verdict. See reports/decisions.md section 13.
#: `blocked_insufficient_events` is distinct from both again: the hypothesis was never
#: run at all, because arithmetic done BEFORE any test showed no route could carry a
#: verdict. Uninformative means it ran and could not inform; blocked means it should not
#: run. Keeping them apart is what stops a scheduling decision from later reading as a
#: finding about the market.
ALLOWED_STATUSES: Final[frozenset[str]] = frozenset({
    "untested", "stage1_inconclusive", "stage1_uninformative", "stage1_passed",
    "blocked_insufficient_events", "retired", "excluded", "dead",
})

#: Statuses that mean "will never be scheduled". Each needs a reason field.
RESOLVED_STATUSES: Final[frozenset[str]] = frozenset({
    "stage1_inconclusive", "stage1_uninformative", "stage1_passed",
    "blocked_insufficient_events", "retired", "excluded", "dead",
})

#: §5 Stage 4 needs two genuinely different instruments. MNQ and MGC are uncorrelated,
#: which is what makes the gate real here; ES/YM/RTY are ρ≈0.9 with NQ and are robustness
#: checks only, so they must never appear as a hypothesis's declared symbols.
STAGE4_INSTRUMENTS: Final[frozenset[str]] = frozenset({"MNQ", "MGC"})
ROBUSTNESS_ONLY: Final[frozenset[str]] = frozenset({"ES", "YM", "RTY", "NQ"})

REG: Final[dict[str, dict[str, Any]]] = {
    e["id"]: e for e in yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
}
CATALOG_TEXT: Final[str] = (CATALOG.read_text(encoding="utf-8")
                            + LEVEL_CATALOG.read_text(encoding="utf-8"))


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
    assert all(re.fullmatch(r"[FL]\d\d", i) for i in ids), ids


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
            if entry.get("is_control"):
                # Controls are never scheduled by test_order - they run alongside whatever
                # they are controlling for - so there is no order for them to have lost.
                continue
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
        "stage1_uninformative": "stage1_reason",
        "blocked_insufficient_events": "blocked_reason",
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
        if entry.get("stage4_reachable") is False:
            # Declared unreachable with a reason, which is honest. The alternative - padding
            # the symbol list with an instrument the mechanism does not hold in - is the F02
            # error and is worse than admitting the ceiling.
            assert entry.get("stage4_reason"), (
                f"{hid} declares Stage 4 unreachable but gives no reason"
            )
            continue
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
        assert re.search(rf"^#+ {hid} — ", CATALOG_TEXT, re.M), (
            f"{hid} is in the registry but has no section in {CATALOG.name}"
        )


@pytest.mark.integrity
def test_every_catalog_entry_appears_in_the_registry() -> None:
    found = set(re.findall(r"^#+ ([FL]\d\d) — ", CATALOG_TEXT, re.M))
    assert found == set(REG), (
        f"catalog and registry disagree: only in catalog {sorted(found - set(REG))}, "
        f"only in registry {sorted(set(REG) - found)}"
    )


@pytest.mark.integrity
def test_the_two_excluded_entries_are_the_expected_ones() -> None:
    """F12, F13 and L11 are excluded; assert the registry agrees and nothing else crept in.

    Pinned explicitly because "excluded" is the one status that costs zero trials, which
    makes it the cheapest place to hide a hypothesis someone did not want to test.

    F12, F13 - excluded at registration on event count and premise; named in the catalog.
    L11    - WITHDRAWN 2026-09-11 after measurement showed the registered condition was
             never a breakout test: it fired on the first bar it examined for every level in
             every session, `kbars` shifted entry by k-1 bars rather than selecting events,
             and the two band boundaries fired at identical (row, minute). Never run at
             Stage 1, no trial spent, N unaffected. decisions.md 40.

    Each addition to this set must carry that kind of reason. Adding a name to make the test
    pass, without one, is the thing this assertion exists to catch.
    """
    excluded = {h for h, e in REG.items() if e["status"] == "excluded"}
    assert excluded == {"F12", "F13", "L11"}, excluded
    assert "BELOW FIRING-RATE GATE" in CATALOG_TEXT
    assert "DECAYED" in CATALOG_TEXT


@pytest.mark.integrity
def test_the_controls_are_the_expected_ones() -> None:
    """Which entries are controls, and which one is live.

    F10 and F11 are retired but keep `is_control`: they were controls, and a reader
    tracing why the catalog's control changed needs to find them as controls rather than
    as ordinary retired hypotheses. F14 replaced them - F10 on power, F11 on premise.
    """
    controls = {h for h, e in REG.items() if e.get("is_control")}
    assert controls == {"F10", "F11", "F14", "L10"}, controls
    for hid in controls:
        assert REG[hid]["grade"] == "D", f"{hid} is a control but is not graded D"

    live = {h for h in controls if REG[h]["status"] == "untested"}
    assert live == {"F14", "L10"}, (
        # F14 covers the fixed-clock regime; L10 covers the level-reaction regime AND
        # validates the placebo machinery every L-series comparison depends on. Two live
        # controls is correct here because they cover different firing patterns.
        f"exactly one live control expected, got {live}. A catalog with no live control "
        f"cannot demonstrate that its harness declines to promote noise; a catalog with "
        f"two invites the question of which one carries the claim."
    )
    assert REG["F14"]["param_cap"] == 0 and REG["L10"]["param_cap"] == 0, (
        "the control must have no free parameters at all - anything sweepable could be "
        "tuned into passing or failing, which is the one thing a control may not permit"
    )


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


@pytest.mark.integrity
def test_uninformative_entries_do_not_claim_a_verdict() -> None:
    """An uninformative run must not read as evidence.

    The whole reason this status exists is that a null from an underpowered cell looks
    identical to a null from a powered one in a results table. So the reason text has to say
    the sample could not support a verdict, and must not claim the mechanism was refuted.
    """
    for hid, entry in REG.items():
        if entry["status"] != "stage1_uninformative":
            continue
        reason = entry["stage1_reason"].lower()
        assert any(k in reason for k in ("below the swept range", "no route to a verdict",
                                         "not evidence", "could not")), (
            f"{hid} is stage1_uninformative but its reason does not say why no verdict "
            f"was obtainable"
        )
        for banned in ("refuted", "is dead", "no edge exists"):
            assert banned not in reason, (
                f"{hid} is stage1_uninformative but its reason says {banned!r} — an "
                f"unpowered run cannot refute anything"
            )


@pytest.mark.integrity
def test_every_hypothesis_has_a_declared_or_measured_firing_rate() -> None:
    """An uncounted firing rate must BLOCK, never fall through to the data ceiling.

    This is the §13 regression guard. The old gate treated a missing rate as "no event
    constraint", which silently granted a hypothesis every observation in the sample
    precisely where least was known about it. Every registered hypothesis must now either
    declare a per-cell rate its condition determines, or have one measured and cached.
    """
    from futuresres.reporting.detectability import (
        MEASURED,
        SCAN_POSITIONS,
        SCAN_POSITIONS_DISJOINT,
    )

    measured_ids = {k[0] for k in MEASURED}
    for hid, entry in REG.items():
        if entry["status"] == "excluded":
            continue
        if entry.get("is_control"):
            # A control does not spend trials and is not "scheduled" in the sense the gate
            # means. Its own rate still gets measured - it just is not a precondition.
            continue
        if entry.get("schedulable") is False:
            # Already unschedulable for a recorded reason. The gate's job is to stop an
            # UNMEASURED hypothesis being scheduled; one that is blocked anyway is not a
            # loophole, and demanding a measurement before registration would invert the
            # order the catalog works in.
            continue
        assert hid in measured_ids, (
            f"{hid} has no MEASURED firing rate and therefore cannot be scheduled. A "
            f"declared rate does not substitute - §21 showed one wrong by a factor of "
            f"forty, and no test can check a declaration because it has no independent "
            f"source. Run `python -m futuresres.reporting.measured_rates`."
        )
        assert hid in SCAN_POSITIONS and hid in SCAN_POSITIONS_DISJOINT, (
            f"{hid} is missing a scan-position or disjointness declaration; without both, "
            f"its aggregate route cannot be assessed"
        )


@pytest.mark.integrity
def test_an_unknown_hypothesis_id_blocks_rather_than_clearing() -> None:
    """The DEFAULT for something nobody has thought about must be 'blocked'."""
    from futuresres.reporting.detectability import DECLARED_ESTIMATE, MEASURED

    unknown = "F99_never_registered"
    assert not any(k[0] == unknown for k in MEASURED), (
        "an unmeasured hypothesis must be absent from MEASURED, which is what blocks it"
    )
    # A declaration must not rescue it even if one existed.
    assert DECLARED_ESTIMATE.get(unknown) is None


@pytest.mark.integrity
def test_blocked_entries_state_the_arithmetic_not_a_finding() -> None:
    """A blocked hypothesis must not read as though the market was tested and found empty."""
    for hid, entry in REG.items():
        if entry["status"] != "blocked_insufficient_events":
            continue
        reason = entry["blocked_reason"].lower()
        assert any(c.isdigit() for c in reason), (
            f"{hid} is blocked_insufficient_events but its reason quotes no counts - the "
            f"arithmetic is the justification and has to be visible"
        )
        for banned in ("refuted", "no edge", "found nothing", "does not work"):
            assert banned not in reason, (
                f"{hid} is blocked before ever running but its reason says {banned!r}"
            )


@pytest.mark.integrity
def test_the_live_control_states_the_regime_it_validates() -> None:
    """A control validates the event regime it fires in, and no other.

    F14 fires ~9 times a session and so speaks to ~40,000-event samples. Most of this
    catalog's hypotheses fire once a session and reach ~4,000. If the entry did not say so,
    a reader would reasonably take "the control came back empty" as covering the whole
    catalog, which it cannot.
    """
    entry = REG["F14"]
    blob = " ".join(str(v) for v in entry.values()).lower()
    for phrase in ("f03-like", "once-a-session"):
        assert phrase in blob, (
            f"F14 must state that it validates {phrase} regimes explicitly - a control's "
            f"scope is part of the claim it licenses"
        )


@pytest.mark.integrity
def test_a_retired_control_says_which_of_the_two_failures_it_was() -> None:
    """Unpowered and not-a-control are different failures and must not blur together."""
    reasons = {h: REG[h]["retired_reason"].lower()
               for h in ("F10", "F11")}
    assert "unpowered" in reasons["F10"] and "not a control" not in reasons["F10"]
    assert "not a control" in reasons["F11"]
    assert "premise" in reasons["F11"], (
        "F11 failed on premise rather than on sample, and its reason must say so - it was "
        "powered, and recording it as merely another underpowered control would lose the "
        "only interesting thing about it"
    )


@pytest.mark.integrity
def test_declared_rates_never_gate() -> None:
    """The §21 regression guard: `assess` must not consult the declared table.

    Checked on the source, because the failure mode is a future edit reintroducing a
    fallback that looks helpful - "use the declaration when no measurement exists" - which
    is exactly the behaviour that let F02 through.
    """
    import ast as _ast
    import inspect

    from futuresres.reporting import detectability as det

    tree = _ast.parse(inspect.getsource(det))
    fn = next(n for n in tree.body
              if isinstance(n, _ast.FunctionDef) and n.name == "assess")
    names = {n.id for n in _ast.walk(fn) if isinstance(n, _ast.Name)}
    assert "DECLARED_ESTIMATE" not in names, (
        "assess() reads the declared estimate table. Declarations must never gate: they "
        "have no independent source and cannot be checked."
    )
    assert "MEASURED" in names, "assess() must read the measured rates"


@pytest.mark.integrity
def test_every_measured_rate_has_a_source() -> None:
    """A measurement must say how it was obtained, so a stale one can be spotted."""
    import json as _json

    path = ROOT / "reports" / "measured_rates.json"
    assert path.exists(), "measured_rates.json is missing; nothing can be scheduled"
    rows = _json.loads(path.read_text(encoding="utf-8"))
    assert rows
    for r in rows:
        assert r["source"] in ("condition", "cell file"), r
        assert r["firings"] >= 0


@pytest.mark.integrity
def test_every_hypothesis_names_the_instruments_its_mechanism_can_hold_in() -> None:
    """§5.10 Stage 0. Two instruments is not a default.

    F02 ran 72 trials on MGC when its counterparty is the NYSE closing auction, which gold
    does not have. Nothing in the pipeline asked whether the mechanism could hold in both,
    because nothing required the question to be answered.
    """
    for hid, entry in REG.items():
        if entry["status"] == "excluded":
            continue
        mi = entry.get("mechanism_instruments")
        assert mi, (
            f"{hid} does not say which instruments its mechanism can exist in. "
            f"`symbols` records what WILL be run; this records what CAN be run, and the "
            f"two differing is exactly the error §5.10 exists to catch."
        )
        assert mi.get("primary") in STAGE4_INSTRUMENTS, mi
        assert "rationale" in mi and len(mi["rationale"]) > 40, (
            f"{hid}'s instrument choice needs a reason, not just a list"
        )
        declared = {str(s).upper() for s in entry.get("symbols") or []}
        can_hold = {mi["primary"]} | ({mi["secondary"]} if mi.get("secondary") else set())
        overrun = declared - can_hold
        if overrun:
            assert entry["status"] != "untested", (
                f"{hid} is scheduled to run on {sorted(overrun)} but its mechanism cannot "
                f"hold there. Running it would spend trials on an undefined claim."
            )


@pytest.mark.integrity
def test_a_hypothesis_with_an_open_specification_defect_is_not_schedulable() -> None:
    """A vacuous condition with plenty of events is the worst combination there is.

    F05's routes are open on event count while its trigger fires on 79-91% of armings,
    because sigma is measured on the very window compression selects for being quiet. A
    confident-looking result about nothing is what that produces.
    """
    for hid, entry in REG.items():
        if not entry.get("specification_defect"):
            continue
        assert entry.get("schedulable") is False, (
            f"{hid} records a specification defect but is not marked unschedulable"
        )


#: Stage numbering per reports/STAGES.md, adopted 2026-09-12.
VALID_STAGES: Final[frozenset[str]] = frozenset(
    {"S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "n/a"}
)


@pytest.mark.integrity
def test_every_l_series_entry_names_the_stage_it_stopped_at() -> None:
    """One numbering across the programme, and an entry must say where it stopped.

    Before 2026-09-12 the project had names for two of the eight things it does - "Stage 0"
    and "Stage 1" - and no name at all for condition validity. That gap is not cosmetic: it
    is how L11's placebo came to be measured against a condition that fired unconditionally,
    with the S6 numbers looking clean and meaning nothing. Naming the stages is what makes
    "measured S6 before S5" a sentence someone can notice.
    """
    for hid, entry in REG.items():
        if not hid.startswith("L"):
            continue
        stage = entry.get("stopped_at")
        assert stage is not None, (
            f"{hid} does not say which stage it stopped at. See reports/STAGES.md."
        )
        assert stage in VALID_STAGES, (
            f"{hid} gives stopped_at={stage!r}, which is not one of {sorted(VALID_STAGES)}"
        )
        assert entry.get("stopped_at_reason"), (
            f"{hid} names stage {stage} but gives no stopped_at_reason. The stage alone "
            f"says where it halted, not why, and 'why' is the part a later reader needs."
        )


@pytest.mark.integrity
def test_the_stage_reference_exists_and_defines_all_eight() -> None:
    """STAGES.md is the canonical reference; a dangling pointer is worse than none."""
    path = ROOT / "reports" / "STAGES.md"
    assert path.exists(), "reports/STAGES.md is missing"
    text = path.read_text(encoding="utf-8")
    for s in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"):
        assert f"**{s}**" in text, f"STAGES.md does not define {s}"
    # The mapping must survive, or historical decisions.md entries become unreadable.
    assert "Stage 0" in text and "Stage 1" in text, (
        "STAGES.md must map the retired Stage 0 / Stage 1 language"
    )
