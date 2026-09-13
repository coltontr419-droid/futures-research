"""Per-hypothesis detectability. CLAUDE_FUTURES.md §5, §7.

    python -m futuresres.reporting.detectability

WHAT THIS EXISTS TO PREVENT. §7 says that below the detection floor, "nothing found" carries
no information — nothing would have been found either way. The floor sweep
(`reports/calibration_floor.md`) measured where that floor sits, and it is not uniform:
MGC at 180 minutes has only 8,190 independent observations in sixteen years and a floor of
0.3x (about 14 bps), the highest in the study, while MNQ at one minute reaches 0.04481x.

A null from a hypothesis whose usable sample sits below its cell's swept range is **not
evidence of absence**. It is the absence of evidence, and the two look identical in a
results table unless something marks the difference. This module marks it, per hypothesis
and per horizon, BEFORE any Stage 1 runs — so a blocked combination is a scheduling decision
rather than a retrospective excuse for a null.

TWO WAYS A COMBINATION IS BLOCKED, and they are reported separately because they mean
different things:

  UNRESOLVABLE        the sweep never resolved a floor for that cell at any tested sample
                      size, so there is no number to compare against
  BELOW SWEPT RANGE   a floor exists for the cell, but the hypothesis's usable sample is
                      smaller than the smallest sample at which it was resolved — so the
                      floor that applies here is higher than any measured, by an unknown
                      amount

TWO INDEPENDENT CEILINGS, AND A HYPOTHESIS IS CAPPED BY THE LOWER.

  DATA CEILING    how many non-overlapping h-minute observations the sample contains at
                  all. Purely a property of (product, horizon): the sixteen-year sample
                  divided by the holding period.

  EVENT CEILING   how many times the hypothesis's own condition can fire. A once-per-session
                  condition caps at the session count however long the sample is — the
                  constraint that closed S01, S07 and S14 in the crypto catalog.

Reporting only the first would call F01 comfortable at 1-hour holds on the strength of
39,444 available observations, when its condition fires once a session and it actually gets
~4,000. Reporting only the second would miss that MGC 180m cannot be calibrated regardless
of how often anything fires.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import polars as pl
import yaml

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
REPORTS: Final[Path] = ROOT / "reports"
CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
REGISTRY: Final[Path] = ROOT / "hypotheses.yaml"
REPORT: Final[Path] = REPORTS / "detectability.md"

SIGMA_BPS: Final[dict[tuple[str, int], float]] = {
    ("MNQ", 1): 3.9, ("MNQ", 30): 21.4, ("MNQ", 60): 30.4, ("MNQ", 180): 52.2,
    ("MGC", 1): 3.5, ("MGC", 30): 18.2, ("MGC", 60): 26.2, ("MGC", 180): 47.8,
}
COST_BPS: Final[dict[str, float]] = {"MNQ": 0.48, "MGC": 0.65}

#: DECLARED ESTIMATES ONLY. **Nothing here gates anything.** These are what each condition
#: looks like it should fire at, kept because the gap between a declaration and a
#: measurement is itself worth being able to see - F02 declared 1.0 and measured 0.061.
#:
#: The gate reads `MEASURED` above and only that. A hypothesis with a declaration but no
#: measurement is UNSCHEDULABLE, not optimistically cleared.
#:
#: Historical note: this table WAS the gate until 2026-09-02. See decisions.md §21 and §22.
#:
#: Firing rate per SESSION **for a single Stage 1 cell**, not for the hypothesis as a whole.
#:
#: THE DISTINCTION IS THE WHOLE POINT, AND GETTING IT WRONG ONCE ALREADY CORRUPTED THIS GATE.
#: A scan like F03 fires 13 times a session across its 13 RTH slots — but `slot` is a GRID
#: AXIS, so each Stage 1 cell fixes one slot and sees one firing per session. Benjamini-
#: Hochberg tests cells, so the sample that decides a cell is the per-cell one. The earlier
#: version of this table stored the scan-wide count and inflated F03's ceiling 13x, F07's
#: 12x and F04's 2x, marking cells RESOLVABLE whose real samples were far below the swept
#: range. See `reports/decisions.md` section 13.
#:
#: The rule: divide the condition's firing rate by the multiplicity of whichever scanned
#: dimension appears as a grid axis. What is left is what one cell actually sees.
#:
#: THRESHOLD-GATED CONDITIONS DECLARE AN UPPER BOUND UNLESS MEASURED. F01, F06 and F09
#: all fire conditionally - on |r1| > k*ATR, on a confirmed breakout, on a settlement-window
#: move - so their declared 1.0 is the rate at which the OPPORTUNITY arises, not the rate at
#: which the condition triggers. F02 declared 1.0 and actually fired at 0.061. Those three
#: are flagged in THRESHOLD_GATED below and their gate rows must be read as optimistic until
#: measured. See reports/decisions.md section 21.
#:
#: None means UNMEASURED, and is now BLOCKING. It used to fall through to the data ceiling,
#: which silently granted a hypothesis every observation in the sample — the most generous
#: possible assumption, applied precisely where least was known. A rate that has not been
#: measured cannot clear a gate.
DECLARED_ESTIMATE: Final[dict[str, float | None]] = {
    # entry_time is a grid axis; a cell fixes it and fires at most once a session.
    "F01": 1.0,
    # MEASURED 2026-09-02 from the run itself (reports/f02_stage1.md), replacing a
    # declared 1.0 that was wrong by an order of magnitude. F02 is THRESHOLD-GATED - it
    # fires only when |imb| > k*sigma, on 6-23% of rows - and it carries a mandatory
    # pre/post-2021 regime split that halves the sample again. The declared rate counted
    # the OPPORTUNITY, not the TRIGGER. Worst cell across k, era and instrument: 106
    # events over ~1,730 post-2021 rows.
    "F02": 0.061,
    # slot is a grid axis: 13 slots, one firing each per session.
    "F03": 1.0,
    # auction is a grid axis: AM and PM, one firing each per session.
    "F04": 1.0,
    # "arm the setup, then the first close beyond k*sigma" — episodes per session are not
    # stated by the condition and have never been counted. UNMEASURED.
    "F05": None,
    # one opening range per session, whatever W is.
    "F06": 1.0,
    # slot is a grid axis: 12 slots, one firing each per session.
    "F07": 1.0,
    # a continuously evaluated cross-asset agreement test; could fire many times a session
    # or none. UNMEASURED.
    "F08": None,
    # one settlement per instrument per session.
    "F09": 1.0,
    # RSI crossings are irregular and have never been counted. UNMEASURED.
    "F10": None,
    # MA crossovers likewise. UNMEASURED.
    "F11": None,
    # MEASURED before registration (reports/control_candidates.md): 9.2 firings a session
    # on MNQ and 7.9 on MGC - not the 13 the RTH slot count implies, because a slot fires
    # only when a bar exists at that exact minute. The lower of the two is declared, so the
    # gate is never more optimistic than the worse instrument.
    "F14": 7.9,
}

#: What the gate stored BEFORE the section 13 correction — kept so the report can show
#: exactly which combinations the error was clearing. Not used for any live decision.
PREVIOUS_FIRES_PER_SESSION: Final[dict[str, float | None]] = {
    "F01": 1.0, "F02": 1.0, "F03": 13.0, "F04": 2.0, "F05": None,
    "F06": 1.0, "F07": 12.0, "F08": None, "F09": 1.0, "F10": None, "F11": None,
}

#: Conditions whose firing rate is gated by a threshold or confirmation, so a declared
#: rate is an UPPER BOUND rather than a measurement. F02 is no longer listed because it has
#: now been measured; the other three have not been.
THRESHOLD_GATED: Final[frozenset[str]] = frozenset({"F01", "F06", "F09"})

#: How many positions the condition scans per session, each of which becomes its own cell.
#: This buys NO per-cell power — it is a trial-count cost, and it multiplies the aggregate
#: only when the positions are disjoint.
SCAN_POSITIONS: Final[dict[str, int]] = {
    # L12 sweeps m and k at ONE level type and one session, so there is a single scan
    # POSITION - the Asia session's extremes - and nine parameter cells on it.
    "L12": 1,
    # N02: one scan position (the session-open grid levels), three depth cells on it.
    "N02": 1,
    "F01": 2,    # entry_time in {15:00, 15:30}
    "F02": 2,    # window in {Europe, Asia}
    "F03": 13,   # the 13 RTH half-hour slots
    "F04": 2,    # auction in {AM, PM}
    "F05": 1,
    "F06": 1,    # W varies the range length, not the position — all three start at 09:30
    "F07": 12,   # the 12 pre-close half-hour slots
    "F08": 1,
    "F09": 1,    # one settlement time per instrument
    "F10": 1,
    "F11": 1,
    # The 13 slots are not a grid axis here: F14's grid is the three holds, and every slot
    # fires inside a single cell. So there is nothing to pool and nothing to divide by.
    "F14": 1,
}

#: Whether the scanned positions are DISJOINT IN TIME, which decides whether pooling them
#: actually restores sample.
#:
#: F03 scans 13 half-hour slots and each is its own non-overlapping trade — 09:30-10:00 is a
#: different window from 10:00-10:30 — so the pooled series really does hold 13x the
#: observations, and its aggregate is powered even though every cell is not.
#:
#: F07 scans 12 slots but they are 12 PREDICTORS OF ONE TARGET: the catalog regresses the
#: LAST half-hour on each of the first twelve. Every cell enters at the same 15:30 minute on
#: the same day. Pooling them stacks twelve correlated readings of ~4,000 sessions, not
#: 48,000 independent ones, so the aggregate ceiling stays at the per-cell ceiling and the
#: pooling escape route is closed. Treating overlap as sample would be the same error this
#: gate was just corrected for, one level up.
#:
#: F01 is the same trap in miniature: its two entry times are 15:00 and 15:30 but BOTH exit
#: at 15:55, so the two positions overlap for all but thirty minutes and pooling them adds
#: almost nothing.
SCAN_POSITIONS_DISJOINT: Final[dict[str, bool]] = {
    # False: m and k select overlapping subsets of the same reclaim. L04, the same condition
    # on MGC, measured 98% pairwise overlap - so pooling L12's cells would count one
    # observation nine times. The aggregate route is CLOSED and its own registry entry says
    # so; this is the measured version of that assumption.
    "L12": False,
    # False: d in {2,4,8} nests - a cross by 8 points was a cross by 2 first.
    "N02": False,
    "F01": False,   # 15:00 and 15:30 entries share a 15:55 exit
    "F02": True,    # Europe 01:30-04:00 and Asia 19:00-22:00 do not overlap
    "F03": True,    # 13 consecutive non-overlapping half-hour trades
    "F04": True,    # AM exits by 07:30 ET at the longest hold, PM opens at 10:00
    "F05": True,
    "F06": True,
    "F07": False,   # 12 predictors of one 15:30 target
    "F08": True,
    "F09": True,
    "F10": True,
    "F11": True,
    "F14": True,
}


#: THE ONLY SOURCE OF EVENT COUNTS. Written by
#: `python -m futuresres.reporting.measured_rates`, which applies each condition's own
#: threshold, applies any mandatory regime split, and reads a cell file directly for any
#: hypothesis that has already run. Keyed (hypothesis, product, horizon) -> (min, max)
#: independent events across that hypothesis's parameter cells.
#:
#: A hypothesis absent from this file CANNOT BE SCHEDULED. That is the whole design: §21
#: showed that a declared rate can be wrong by a factor of forty and that no test can catch
#: it, because a declaration has no independent source to check against.
def load_measured() -> dict[tuple[str, str, int], tuple[int, int]]:
    path = REPORTS / "measured_rates.json"
    if not path.exists():
        return {}
    out: dict[tuple[str, str, int], list[int]] = {}
    for r in json.loads(path.read_text(encoding="utf-8")):
        key = (r["hypothesis"], r["product"], r["horizon"])
        out.setdefault(key, []).append(int(r["independent"]))
    return {k: (min(v), max(v)) for k, v in out.items()}


MEASURED: Final[dict[tuple[str, str, int], tuple[int, int]]] = load_measured()



@dataclass(slots=True)
class Cell:
    """One (product, horizon) cell of the measured floor sweep."""

    product: str
    horizon: int
    available: int
    resolved: list[tuple[int, float]]      # (n, floor) for rungs that resolved
    unresolved_n: list[int]

    @property
    def ever_resolved(self) -> bool:
        return bool(self.resolved)

    @property
    def smallest_resolving_n(self) -> int | None:
        return min(n for n, _ in self.resolved) if self.resolved else None

    @property
    def best_floor(self) -> float | None:
        return min(f for _, f in self.resolved) if self.resolved else None


def load_cells() -> dict[tuple[str, int], Cell]:
    raw = json.loads((REPORTS / "floor_cache.json").read_text(encoding="utf-8"))
    out: dict[tuple[str, int], Cell] = {}
    for c in raw:
        resolved = [(cur["n"], cur["floor"]) for cur in c["curves"] if cur.get("floor")]
        unresolved = [cur["n"] for cur in c["curves"] if not cur.get("floor")]
        out[(c["product"], c["horizon"])] = Cell(
            c["product"], c["horizon"], c["available"], resolved, unresolved
        )
    return out


#: MNQ began trading in 2019. §3 spliced NQ before it precisely so index hypotheses get
#: sixteen years rather than seven, so the EVENT ceiling is counted on the spliced series —
#: using MNQ alone understates every index hypothesis by more than half.
#:
#: The floor CELLS were measured on MNQ-only data, so the two are not the same span. That
#: is stated in the report rather than papered over.
SPLICED: Final[dict[str, str]] = {"MNQ": "NQ_MNQ_spliced"}


def sessions_and_bars(product: str) -> tuple[int, int]:
    name = SPLICED.get(product, product)
    path = CONTINUOUS / f"{name}.parquet"
    if not path.exists():
        path = CONTINUOUS / f"{product}.parquet"
    bars = pl.read_parquet(path)
    return bars.get_column("session").n_unique(), bars.height


def nearest_measured_horizon(horizon: int, measured: list[int]) -> int:
    """The swept horizon whose floor best describes `horizon`.

    Nearest in LOG space, because the floor responds to sample size and sample size scales
    inversely with the holding period — a 90-minute hold is much closer to 60 than a linear
    distance suggests once both are expressed as observation counts.
    """
    import math

    return min(measured, key=lambda m: abs(math.log(horizon / m)))


@dataclass(slots=True)
class Verdict:
    hypothesis: str
    name: str
    product: str
    horizon: int
    data_ceiling: int
    event_ceiling: int | None          # PER CELL - this gates BH
    aggregate_ceiling: int | None      # pooled across the scan's cells
    scan_positions: int
    effective: int
    proxy_horizon: int
    status: str            # RESOLVABLE | BELOW SWEPT RANGE | UNRESOLVABLE | UNMEASURED
    previous_status: str   # what the pre-section-13 gate said
    previous_effective: int | None
    floor: float | None
    floor_bps: float | None
    note: str

    @property
    def blocked(self) -> bool:
        """MIXED is not blocked outright - some of its cells resolve - but it is not clear
        either, and the per-cell table is what says which. It counts as open here and the
        report names it explicitly."""
        return self.status not in ("RESOLVABLE", "MIXED")


def _previous_verdict(entry: dict, cell: "Cell", data_ceiling: int,
                      sessions: int) -> tuple[str, int | None]:
    """What the gate said BEFORE the section 13 correction, for the report's diff.

    Reproduces the old behaviour exactly: the scan-wide firing rate in the per-cell slot,
    and an unmeasured rate falling through to the data ceiling rather than blocking.
    """
    fires = PREVIOUS_FIRES_PER_SESSION.get(entry["id"])  # the pre-§13 table
    event_ceiling = int(sessions * fires) if fires else None
    effective = min([x for x in (data_ceiling, event_ceiling) if x is not None])
    if not cell.ever_resolved:
        return "UNRESOLVABLE", effective
    if effective < (cell.smallest_resolving_n or 0):
        return "BELOW SWEPT RANGE", effective
    return "RESOLVABLE", effective


def assess(entry: dict, cells: dict[tuple[str, int], Cell],
           session_counts: dict[str, int]) -> list[Verdict]:
    out: list[Verdict] = []
    measured_horizons = sorted({h for _, h in cells})
    positions = SCAN_POSITIONS.get(entry["id"], 1)
    for product in (str(s).upper() for s in entry.get("symbols") or []):
        if product not in session_counts:
            continue
        for horizon in entry["horizon_minutes"]:
            proxy = nearest_measured_horizon(horizon, measured_horizons)
            cell = cells.get((product, proxy))
            if cell is None:
                continue
            sessions = session_counts[product]
            # Data ceiling scales with the hypothesis's OWN horizon, not the proxy's.
            data_ceiling = int(cell.available * proxy / horizon)
            event_ceiling = None
            # Overlapping positions pool into correlated readings of the SAME sessions,
            # so they add no independent observations.
            disjoint = SCAN_POSITIONS_DISJOINT.get(entry["id"], True)
            aggregate_ceiling = (
                event_ceiling * (positions if disjoint else 1)
            ) if event_ceiling else None
            effective = data_ceiling

            prev_status, prev_eff = _previous_verdict(entry, cell, data_ceiling, sessions)

            measured = MEASURED.get((entry["id"], product, horizon))
            if measured is not None:
                # A counted rate supersedes a declared one: it is the same quantity,
                # observed rather than asserted.
                lo, hi = measured
                event_ceiling = lo
                aggregate_ceiling = lo * (positions if disjoint else 1)
                effective = min(lo, data_ceiling)

            if measured is None:
                status = "FIRING RATE UNMEASURED"
                note = ("no MEASURED firing rate exists for this combination, so it cannot "
                        "be scheduled. A declared rate does not substitute: §21 showed one "
                        "wrong by a factor of forty, with no test able to catch it. Run "
                        "`python -m futuresres.reporting.measured_rates`.")
                floor = None
                effective = 0
                aggregate_ceiling = None
            elif measured is not None and cell.ever_resolved and (
                    measured[0] < (cell.smallest_resolving_n or 0)
                    <= min(measured[1], data_ceiling)):
                status = "MIXED"
                note = (f"measured {measured[0]:,}-{measured[1]:,} independent events "
                        f"across parameter cells, straddling the "
                        f"{cell.smallest_resolving_n:,} at which a floor resolves - some "
                        f"cells of this hypothesis can carry a verdict and some cannot")
                floor = cell.best_floor
            elif not cell.ever_resolved:
                status = "UNRESOLVABLE"
                note = (f"the sweep never resolved a floor for {product} {proxy}m at any "
                        f"tested sample size")
                floor = None
            elif effective < (cell.smallest_resolving_n or 0):
                status = "BELOW SWEPT RANGE"
                note = (f"{effective:,} usable observations is below the smallest sample "
                        f"that resolved a floor ({cell.smallest_resolving_n:,})")
                floor = None
            else:
                status = "RESOLVABLE"
                usable = [(n, f) for n, f in cell.resolved if n <= effective]
                floor = min(f for _, f in usable) if usable else cell.best_floor
                note = ""
            sigma = SIGMA_BPS.get((product, proxy))
            out.append(Verdict(
                entry["id"], entry["name"], product, horizon, data_ceiling,
                event_ceiling, aggregate_ceiling, positions, effective, proxy, status,
                prev_status, prev_eff, floor,
                floor * sigma if (floor and sigma) else None, note,
            ))
    return out


def render(verdicts: list[Verdict], cells: dict[tuple[str, int], Cell],
           session_counts: dict[str, int]) -> str:
    w: list[str] = []
    a = w.append
    a("# Per-hypothesis detectability")
    a("")
    a("Generated by `python -m futuresres.reporting.detectability`. "
      "CLAUDE_FUTURES.md §5, §7.")
    a("")
    a("§7: below the detection floor, \"nothing found\" carries no information, because "
      "nothing would have been found either way. This maps every registered hypothesis onto "
      "the measured floor cells **before** Stage 1 runs, so an unresolvable combination is a "
      "scheduling decision rather than a retrospective excuse for a null.")
    a("")
    a("## The event ceiling is counted PER CELL")
    a("")
    a("Benjamini-Hochberg tests cells, so the sample that decides a cell is the sample that "
      "cell sees. A scan fires many times a session, but if the scanned dimension is a grid "
      "axis then each cell fixes it and sees **one** firing per session. The scan breadth "
      "buys trials, not power.")
    a("")
    a("| hypothesis | scanned positions | per-cell fires/session | aggregate fires/session |")
    a("|---|---|---|---|")
    for hid in sorted(SCAN_POSITIONS):
        f = DECLARED_ESTIMATE.get(hid)
        n = SCAN_POSITIONS[hid]
        if f is None:
            continue
        mark = " **<-**" if n > 1 else ""
        a(f"| {hid} | {n} | {f:g} | {f * n:g}{mark}")
    a("")
    a("An earlier version of this gate stored the **aggregate** rate in the per-cell slot, "
      "inflating F03's ceiling 13x, F07's 12x and F04's 2x. Cells were marked RESOLVABLE "
      "whose real per-cell samples sat far below the swept range. The rows below are the "
      "corrected ones; `reports/decisions.md` section 13 records what it changed.")
    a("")

    blocked = [v for v in verdicts if v.blocked]
    affected = sorted({v.hypothesis for v in blocked})
    a(f"**{len(blocked)} of {len(verdicts)} (hypothesis, instrument, horizon) combinations "
      f"cannot support a null**, across {len(affected)} hypotheses: "
      f"{', '.join(affected) if affected else 'none'}.")
    a("")

    # ------------------------------------------------ what the correction changed
    newly = [v for v in verdicts if v.previous_status == "RESOLVABLE" and v.blocked]
    still = [v for v in verdicts if v.previous_status == "RESOLVABLE" and not v.blocked]
    a("## What the correction blocked")
    a("")
    a(f"**{len(newly)} combinations were previously cleared and are now blocked.** "
      f"{len(still)} remain cleared.")
    a("")
    if newly:
        a("| hypothesis | product | horizon | old ceiling | old verdict | new ceiling | now | why |")
        a("|---|---|---|---|---|---|---|---|")
        for v in sorted(newly, key=lambda v: (v.hypothesis, v.product, v.horizon)):
            measured_here = (v.hypothesis, v.product, v.horizon) in MEASURED
            if v.status == "FIRING RATE UNMEASURED":
                why = "firing rate never measured"
            elif measured_here or v.hypothesis in MEASURED_RATE_IDS:
                # A measured rate supersedes a declared one; when it closes a row the cause
                # is the rate itself, not the scan arithmetic.
                why = "measured firing rate far below the declared one"
            elif v.scan_positions > 1:
                why = f"per-cell sample is {v.scan_positions}x smaller than counted"
            else:
                why = "per-cell sample below the swept range"
            a(f"| {v.hypothesis} | {v.product} | {v.horizon}m | "
              + (f"{v.previous_effective:,}" if v.previous_effective else "—")
              + f" | {v.previous_status} | {v.effective:,} | **{v.status}** | {why} |")
        a("")
    a("Two separate causes are mixed in that table and they are not equally bad. The "
      "**scan-multiplicity** rows (F03, F04, F07) were arithmetic: the gate counted firings "
      "the cell never sees. The **unmeasured** rows (F05, F08, F10, F11) were worse — a "
      "missing firing rate used to fall through to the data ceiling, which handed a "
      "hypothesis every observation in the sample precisely where least was known about it. "
      "Both now block.")
    a("")

    unmeasured = sorted({v.hypothesis for v in verdicts
                         if v.status == "FIRING RATE UNMEASURED"})
    if unmeasured:
        a(f"**{', '.join(unmeasured)} are blocked on a missing measurement, not on a "
          f"finding.** Their conditions do not state a per-session firing rate and it has "
          f"never been counted: F05 arms on a volatility-compression episode, F08 on a "
          f"continuously evaluated cross-asset agreement, F10 and F11 on indicator "
          f"crossings. Counting those rates is a data measurement, not a Stage 1 run, and "
          f"it is what unblocks them.")
        a("")

    # ------------------------------------------------ verdict routes
    a("## Verdict routes, per hypothesis")
    a("")
    a("Two routes exist. **Per-cell** is the ordinary one: each cell tested, "
      "Benjamini-Hochberg across them. **Aggregate** pools the scanned positions into one "
      "series — available only when those positions are disjoint in time, because "
      "overlapping ones stack correlated readings of the same sessions rather than "
      "accumulating independent observations.")
    a("")
    a("| hypothesis | cells open | positions | disjoint | per-cell route | aggregate route |")
    a("|---|---|---|---|---|---|")
    for hid in sorted({v.hypothesis for v in verdicts}):
        vs = [v for v in verdicts if v.hypothesis == hid]
        pos = vs[0].scan_positions
        dj = SCAN_POSITIONS_DISJOINT.get(hid, True)
        open_cells = [v for v in vs if not v.blocked]
        if vs[0].status == "FIRING RATE UNMEASURED":
            cell_route = "**unknown** — rate unmeasured"
        elif open_cells:
            cell_route = (f"**open** ({len(open_cells)}/{len(vs)}: "
                          + ", ".join(f"{v.product} {v.horizon}m" for v in open_cells) + ")")
        else:
            cell_route = "**closed** — every cell below the swept range"
        if pos == 1:
            agg_route = "n/a — nothing to pool"
        elif not dj:
            agg_route = "**closed** — positions overlap"
        elif vs[0].status == "FIRING RATE UNMEASURED":
            agg_route = "**unknown** — rate unmeasured"
        else:
            ok = []
            for v in vs:
                c = cells.get((v.product, v.proxy_horizon))
                agg = min(v.aggregate_ceiling, v.data_ceiling) if v.aggregate_ceiling else None
                if c and c.ever_resolved and agg and agg >= (c.smallest_resolving_n or 0):
                    ok.append(v)
            agg_route = (f"**open** ({len(ok)}/{len(vs)})" if ok
                         else "**closed** — pooled sample still below range")
        open_label = ("rate unmeasured" if vs[0].status == "FIRING RATE UNMEASURED"
                      else f"{len(open_cells)}/{len(vs)}")
        a(f"| {hid} | {open_label} | {pos} | "
          + ("yes" if dj else "**no**") + f" | {cell_route} | {agg_route} |")
    a("")
    a("**F07 is the only hypothesis with both routes closed on a measurement rather than a "
      "finding** — its cells are underpowered and its positions overlap, so nothing it "
      "produces can be evidence. That is why it is recorded `stage1_uninformative` rather "
      "than retired.")
    a("")

    scans = [v for v in verdicts if v.scan_positions > 1]
    if scans:
        a("## Where a scan's verdict can still live: the aggregate")
        a("")
        a("A scan whose every cell is below the swept range is not thereby untestable. "
          "Pooling its cells restores the sample — the aggregate return series across all "
          "scanned positions is the hypothesis's own portfolio, and it answers the question "
          "the scan is really asking: does the effect exist ANYWHERE in this session "
          "structure. It cannot say which position carries it. That is the trade.")
        a("")
        a("| hypothesis | product | horizon | per-cell | per-cell status | positions | aggregate | aggregate status |")
        a("|---|---|---|---|---|---|---|---|")
        for v in sorted(scans, key=lambda v: (v.hypothesis, v.product, v.horizon)):
            cell = cells.get((v.product, v.proxy_horizon))
            agg = v.aggregate_ceiling
            eff_agg = min(agg, v.data_ceiling) if agg else None
            if cell is None or not cell.ever_resolved or eff_agg is None:
                agg_status = "UNRESOLVABLE"
            elif eff_agg < (cell.smallest_resolving_n or 0):
                agg_status = "BELOW SWEPT RANGE"
            else:
                agg_status = "**RESOLVABLE**"
            dj = SCAN_POSITIONS_DISJOINT.get(v.hypothesis, True)
            a(f"| {v.hypothesis} | {v.product} | {v.horizon}m | {v.effective:,} | "
              f"{v.status} | {v.scan_positions} "
              + ("disjoint" if dj else "**overlapping**")
              + f" | {eff_agg:,} | {agg_status} |")
        a("")
        a("**F03's aggregate is powered; F07's is not, and the difference is overlap.** "
          "Both have per-cell samples 12-13x smaller than the gate previously credited them "
          "with, so every individual cell of both is uninformative. F03's 13 slots are "
          "disjoint trades, so pooling genuinely multiplies its observations. F07's 12 slots "
          "are twelve predictors of the SAME last-half-hour window, entered on the same "
          "minute of the same session, so pooling stacks correlated readings of one ~4,000 "
          "session sample and adds nothing. **F07 has no route to a verdict at any level.**")
        a("")

    a("## The measured cells")
    a("")
    a("| product | horizon | independent obs | rungs resolved | smallest resolving n | best floor |")
    a("|---|---|---|---|---|---|")
    for (product, horizon), c in sorted(cells.items()):
        a(f"| {product} | {horizon}m | {c.available:,} | "
          f"{len(c.resolved)}/{len(c.resolved) + len(c.unresolved_n)} | "
          + (f"{c.smallest_resolving_n:,}" if c.smallest_resolving_n else "—") + " | "
          + (f"{c.best_floor:.4g}×" if c.best_floor else "**never resolved**") + " |")
    a("")

    if blocked:
        a("## Blocked combinations")
        a("")
        a("A Stage 1 null from any of these must be recorded as **uninformative**, not as "
          "evidence against the hypothesis.")
        a("")
        a("| id | hypothesis | instrument | horizon | usable obs | limited by | status |")
        a("|---|---|---|---|---|---|---|")
        for v in sorted(blocked, key=lambda v: (v.hypothesis, v.product, v.horizon)):
            limiter = ("event rate" if v.event_ceiling is not None
                       and v.event_ceiling <= v.data_ceiling else "data")
            a(f"| {v.hypothesis} | {v.name} | {v.product} | {v.horizon}m | "
              f"{v.effective:,} | {limiter} | **{v.status}** |")
        a("")
        for v in sorted(blocked, key=lambda v: (v.hypothesis, v.product, v.horizon))[:12]:
            a(f"- `{v.hypothesis}` {v.product} {v.horizon}m — {v.note}")
        a("")

    a("## All combinations")
    a("")
    a("| id | instrument | horizon | data ceiling | event ceiling | usable | floor | floor bps | cost | status |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for v in sorted(verdicts, key=lambda v: (v.hypothesis, v.product, v.horizon)):
        cost = COST_BPS[v.product]
        a(f"| {v.hypothesis} | {v.product} | {v.horizon}m | {v.data_ceiling:,} | "
          + (f"{v.event_ceiling:,}" if v.event_ceiling is not None else "—")
          + f" | **{v.effective:,}** | "
          + (f"{v.floor:.4g}×" if v.floor else "—") + " | "
          + (f"**{v.floor_bps:.2f}**" if v.floor_bps else "—")
          + f" | {cost} | {v.status} |")
    a("")

    a("## How the ceilings were computed")
    a("")
    for product, sessions in sorted(session_counts.items()):
        via = " (on the spliced NQ+MNQ series, per §3)" if product in SPLICED else ""
        a(f"- **{product}**: {sessions:,} trading sessions in the sample{via}.")
    a("")
    a("> The event ceiling for MNQ is counted on the **spliced NQ+MNQ series** — that is why "
      "§3 built it — while the floor cells were measured on **MNQ-only** data. The spans "
      "differ. The ceiling says what a hypothesis can reach; the floor says what the "
      "pipeline can see; a combination is blocked when the first falls short of the second.")
    a("")
    a("**Data ceiling** is the count of non-overlapping observations at the hypothesis's own "
      "holding period. **Event ceiling** is sessions × the condition's own firing rate, read "
      "from the catalog: F01/F02/F06/F09 fire once a session, F03 scans 13 RTH half-hour "
      "slots, F04 has two LBMA auctions a business day, F07 scans 12. F05 and F08 have "
      "conditions whose firing rate is not fixed a priori, so only the data ceiling applies "
      "and their true event count must be measured at Stage 1 before a null is read.")
    a("")
    a("A hypothesis is capped by the LOWER of the two. Reporting only the data ceiling would "
      "call a once-per-session hypothesis comfortable on the strength of observations its "
      "condition can never reach.")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.detectability")
    ap.parse_args(argv)
    if not (REPORTS / "floor_cache.json").exists():
        print("FAILED: reports/floor_cache.json missing — run the floor sweep first",
              file=sys.stderr)
        return 1

    cells = load_cells()
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    session_counts = {p: sessions_and_bars(p)[0] for p in {c[0] for c in cells}}

    verdicts: list[Verdict] = []
    for entry in registry:
        if entry["status"] in ("excluded", "dead"):
            continue
        verdicts.extend(assess(entry, cells, session_counts))

    REPORT.write_text(render(verdicts, cells, session_counts), encoding="utf-8")
    blocked = [v for v in verdicts if v.blocked]
    print(f"{len(verdicts)} combinations assessed, {len(blocked)} blocked")
    for v in sorted(blocked, key=lambda v: (v.hypothesis, v.product, v.horizon)):
        print(f"  {v.status:<20} {v.hypothesis} {v.product} {v.horizon}m "
              f"({v.effective:,} usable)")
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
