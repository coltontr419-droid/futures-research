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
CELL_FIRES_PER_SESSION: Final[dict[str, float]] = {
    "F01": 1.0, "F02": 1.0, "F03": 1.0, "F04": 1.0, "F05": None,
    "F06": 1.0, "F07": 1.0, "F08": None, "F09": 1.0, "F10": None, "F11": None,
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
SCAN_POSITIONS_DISJOINT: Final[dict[str, bool]] = {
    "F01": True, "F02": True, "F03": True, "F04": True, "F05": True,
    "F06": True, "F07": False, "F08": True, "F09": True, "F10": True, "F11": True,
}

#: How many positions the condition scans per session, each of which becomes its own cell.
#: This buys NO per-cell power — it is a trial-count cost, and it multiplies the aggregate.
SCAN_POSITIONS: Final[dict[str, int]] = {
    "F01": 1, "F02": 1, "F03": 13, "F04": 2, "F05": 1,
    "F06": 1, "F07": 12, "F08": 1, "F09": 1, "F10": 1, "F11": 1,
}


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
    status: str            # RESOLVABLE | BELOW SWEPT RANGE | UNRESOLVABLE
    floor: float | None
    floor_bps: float | None
    note: str

    @property
    def blocked(self) -> bool:
        return self.status != "RESOLVABLE"


def assess(entry: dict, cells: dict[tuple[str, int], Cell],
           session_counts: dict[str, int]) -> list[Verdict]:
    out: list[Verdict] = []
    measured_horizons = sorted({h for _, h in cells})
    fires = CELL_FIRES_PER_SESSION.get(entry["id"])
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
            event_ceiling = int(sessions * fires) if fires else None
            # Overlapping positions pool into correlated readings of the SAME sessions,
            # so they add no independent observations.
            disjoint = SCAN_POSITIONS_DISJOINT.get(entry["id"], True)
            aggregate_ceiling = (
                event_ceiling * (positions if disjoint else 1)
            ) if event_ceiling else None
            effective = min([x for x in (data_ceiling, event_ceiling) if x is not None])

            if not cell.ever_resolved:
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
                event_ceiling, aggregate_ceiling, positions, effective, proxy, status, floor,
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
        f = CELL_FIRES_PER_SESSION.get(hid)
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
