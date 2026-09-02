"""The only sanctioned way to run a Stage 1 hypothesis. CLAUDE_FUTURES.md §6.

    with stage1_run("F04", provenance="native") as log:
        cells = run(...)
        log.record(cells)

WHY THIS EXISTS. `stats/trials.py` — the hash-chained append-only trial log — was ported
from the crypto repo with its tests, and its tests passed, and **no runner ever called it**.
Three hypotheses were run and 342 trials spent before anyone noticed, because N was being
reconstructed by counting rows in output files. A log nothing writes to is not a weaker
control than no log; it is worse, because its passing tests imply a discipline that is not
being practised.

WHAT THE CONTEXT MANAGER GUARANTEES. On clean exit it asserts the log actually grew. A
runner that computes cells and forgets to record them raises `UnloggedRun` instead of
exiting 0 with a tidy report — the failure is loud and happens in the run that caused it,
not three weeks later when someone recomputes N.

It does NOT guarantee the count is right, only that it is non-zero. Nothing can verify from
inside that every cell was passed in. That is what `tests/test_trial_logging.py` checks
structurally, by refusing to let a runner module exist without going through here.

PROVENANCE IS PART OF THE RECORD, not a comment. Trials reconstructed from output files
after the fact are marked `reconstructed`, because they are weaker evidence than natively
logged ones: their timestamps are the backfill's, their ordering within a run is lost, and
nothing proves the output file was not edited. They still count toward N — a look at the
data is a look at the data — but a reader must be able to tell the two apart without
consulting git history.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Final, Iterable, Iterator, Sequence

from futuresres.stats.trials import Trial, TrialLog

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
TRIAL_LOG: Final[Path] = ROOT / "trials.jsonl"

#: How a record reached the log. Part of every trial's note, never inferred later.
PROVENANCE: Final[frozenset[str]] = frozenset({
    "native",         # written by the runner, in the run that produced it
    "reconstructed",  # backfilled from an output file after the fact
})


class UnloggedRun(RuntimeError):
    """A Stage 1 run finished without appending anything to the trial log."""


def _as_dict(cell: Any) -> dict[str, Any]:
    if is_dataclass(cell):
        return asdict(cell)
    if isinstance(cell, dict):
        return dict(cell)
    raise TypeError(f"cannot record {type(cell).__name__} as a trial")


class Recorder:
    """Accumulates cells and appends them as trials."""

    def __init__(self, hypothesis_id: str, log: TrialLog, provenance: str,
                 date_range: tuple[str, str], note: str = "") -> None:
        if provenance not in PROVENANCE:
            raise ValueError(f"provenance must be one of {sorted(PROVENANCE)}")
        self.hypothesis_id = hypothesis_id
        self.log = log
        self.provenance = provenance
        self.date_range = date_range
        self.note = note
        self.written = 0

    def record(self, cells: Iterable[Any],
               param_keys: Sequence[str] | None = None) -> int:
        """Append one trial per cell. Returns how many were written."""
        for cell in cells:
            d = _as_dict(cell)
            symbol = str(d.get("product") or d.get("symbol") or "?")
            keys = param_keys or [
                k for k in d
                if k not in {"product", "symbol", "events", "mean_bps", "sharpe",
                             "p_value", "hit_rate", "separated", "blocked", "reason",
                             "firings", "independent", "per_session", "note"}
            ]
            note = f"provenance={self.provenance}"
            if self.note:
                note += f"; {self.note}"
            if d.get("blocked"):
                note += "; UNINFORMATIVE: below the swept range, not evidence"
            if d.get("reason"):
                note += f"; {d['reason']}"
            self.log.append(Trial(
                trial_id=self.log.next_id(),
                hypothesis_id=self.hypothesis_id,
                params={k: d[k] for k in keys if k in d},
                symbol=symbol,
                date_range=self.date_range,
                status="completed",
                sharpe=d.get("sharpe"),
                trade_count=d.get("events") or d.get("independent"),
                note=note,
            ))
            self.written += 1
        return self.written


@contextmanager
def stage1_run(hypothesis_id: str, *, provenance: str = "native",
               date_range: tuple[str, str] = ("2010-01-01", "2026-08-28"),
               note: str = "", path: Path | None = None) -> Iterator[Recorder]:
    """Run a hypothesis with logging enforced.

    Raises `UnloggedRun` on clean exit if nothing was appended. An exception inside the
    block propagates untouched — a crashed run has its own story and forcing a second
    failure on top of it would hide the first.
    """
    log = TrialLog(path or TRIAL_LOG)
    before = len(log)
    recorder = Recorder(hypothesis_id, log, provenance, date_range, note)
    yield recorder
    after = len(log)
    if after <= before:
        raise UnloggedRun(
            f"{hypothesis_id} completed without appending to {log.path}. Every Stage 1 "
            f"run spends trials and every trial must be logged before N can mean "
            f"anything — call recorder.record(cells) inside the block."
        )
