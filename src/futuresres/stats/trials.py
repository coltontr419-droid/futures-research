"""Append-only trial log — CLAUDE.md §6, build order step 5.

Every backtest run, including abandoned and hand-tweaked ones, appends one JSON object per
line to `trials.jsonl`. The count `N` is the input to the Deflated Sharpe Ratio and to
every other correction in §6, and **all of them move in the optimistic direction as N
falls**. That single fact drives the whole design:

APPEND-ONLY IS ENFORCED, NOT REQUESTED. Records are chained by hash: each carries the
SHA256 of the record before it. Editing any earlier line, deleting one, or reordering the
file breaks the chain at that point and `verify_chain()` says exactly where. Git history
proves nothing was removed between commits; the chain proves it between them too.

SUPERSEDING DOES NOT REDUCE N. A trial later found to be a bug is superseded by a new
record referencing it — never edited, never deleted. The buggy trial still consumed a look
at the data, so it still counts toward the multiple-testing correction. `n_for_deflation()`
returns every record for exactly this reason; if that ever returns fewer than the number of
lines in the file, the deflation math has been quietly weakened.

NON-FINITE METRICS RAISE. NaN and infinity are not JSON. Rather than write a file that
cannot be read back, an undefined metric must be recorded as null with a status that says
why — a profit factor of "infinity" is not a result, it is a run with no losing trades.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final, Iterator

#: Allowed `status` values. A closed set so a typo cannot silently create a new category
#: that later filters miss — "abandonded" would otherwise vanish from every count.
STATUSES: Final[frozenset[str]] = frozenset({
    "completed",    # ran to completion; metrics are meaningful
    "abandoned",    # stopped early or by hand; still a look at the data, still counts
    "error",        # crashed or produced unusable output; still a trial
    "superseded",   # replaced by a later record; retained, and still counts toward N
})

#: Numeric metric fields. Present so validation and NaN handling stay in one place.
METRIC_FIELDS: Final[tuple[str, ...]] = (
    "sharpe", "sortino", "total_return", "max_dd", "profit_factor",
)

GENESIS: Final[str] = ""  # prev_hash of the first record


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical(record: dict[str, Any]) -> str:
    """Byte-stable JSON for hashing and for the file itself.

    Sorted keys and no incidental whitespace, so the same record always hashes the same
    way regardless of dict insertion order.
    """
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)


def record_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(record).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Trial:
    """One backtest run. Fields follow §6's schema."""

    trial_id: str
    hypothesis_id: str
    params: dict[str, Any]
    symbol: str
    date_range: tuple[str, str]
    status: str
    timestamp: str = field(default_factory=_utc_now)
    sharpe: float | None = None
    sortino: float | None = None
    total_return: float | None = None
    max_dd: float | None = None
    trade_count: int | None = None
    profit_factor: float | None = None
    supersedes: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(
                f"status {self.status!r} is not one of {sorted(STATUSES)}. A new status "
                f"must be added to STATUSES deliberately, not by typo."
            )
        if not self.trial_id:
            raise ValueError("trial_id is required")
        if len(self.date_range) != 2:
            raise ValueError(f"date_range must be (start, end), got {self.date_range!r}")
        for name in METRIC_FIELDS:
            value = getattr(self, name)
            if value is not None and not math.isfinite(value):
                raise ValueError(
                    f"{name}={value!r} is not finite and cannot be written as JSON. "
                    f"Record it as None and set a status explaining why — an infinite "
                    f"profit factor is a run with no losing trades, not a result."
                )

    def to_record(self) -> dict[str, Any]:
        out = asdict(self)
        out["date_range"] = list(self.date_range)
        return out

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Trial":
        data = {k: v for k, v in record.items() if k != "prev_hash"}
        data["date_range"] = tuple(data["date_range"])
        return cls(**data)


@dataclass(frozen=True, slots=True)
class ChainResult:
    ok: bool
    n_records: int
    broken_at: int | None = None
    detail: str = ""


class TrialLog:
    """The append-only log itself.

    Opening does not read the file; `append` reads the existing ids once to reject a
    duplicate `trial_id`, because two trials sharing an id makes N ambiguous and silently
    corrupts every correction downstream.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    # ── reading ────────────────────────────────────────────────────────────

    def raw_records(self) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{self.path}:{lineno}: not valid JSON — {exc}") from exc

    def read_all(self) -> list[Trial]:
        return [Trial.from_record(r) for r in self.raw_records()]

    def __len__(self) -> int:
        return sum(1 for _ in self.raw_records())

    def n_for_deflation(self) -> int:
        """N for §6's corrections: every record, superseded ones included.

        A superseded trial still consumed a look at the data. Excluding it would lower N,
        and every correction in §6 gets more optimistic as N falls.
        """
        return len(self)

    def ids(self) -> set[str]:
        return {r["trial_id"] for r in self.raw_records()}

    def next_id(self, prefix: str = "t") -> str:
        """Sequential id, one past the HIGHEST already used with this prefix.

        It used to be derived from the record COUNT, on the reasoning that an append-only
        log only ever grows so the count is the high-water mark. That reasoning failed the
        moment records were moved out: after the control migration the log held 486 records
        whose ids ran to t00492, and the next count-derived id was t00487 - already taken.
        The append raised rather than silently duplicating, which is the log working, but
        the id scheme was the thing at fault.

        Taking the maximum makes the id monotonic regardless of what the log contains.
        """
        highest = 0
        for record in self.raw_records():
            tid = record["trial_id"]
            if tid.startswith(prefix):
                suffix = tid[len(prefix):]
                if suffix.isdigit():
                    highest = max(highest, int(suffix))
        return f"{prefix}{highest + 1:05d}"

    # ── writing ────────────────────────────────────────────────────────────

    def _tip_hash(self) -> str:
        tip = GENESIS
        for record in self.raw_records():
            tip = record_hash(record)
        return tip

    def append(self, trial: Trial) -> dict[str, Any]:
        """Append one record. The only write path. Never rewrites what is on disk."""
        if trial.trial_id in self.ids():
            raise ValueError(
                f"trial_id {trial.trial_id!r} is already in the log. Ids must be unique — "
                f"a repeated id makes N ambiguous. Use next_id(), or supersede()."
            )
        record = trial.to_record()
        record["prev_hash"] = self._tip_hash()

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(canonical(record) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return record

    def supersede(self, old_id: str, trial: Trial, reason: str) -> dict[str, Any]:
        """Record that an earlier trial was wrong, by appending — never by editing.

        Both records remain and both count toward N. The old one is not marked in place;
        marking it would require a rewrite, which is the thing this log does not do.
        """
        if old_id not in self.ids():
            raise ValueError(f"cannot supersede {old_id!r}: not in the log")
        if trial.supersedes != old_id:
            raise ValueError(
                f"trial.supersedes is {trial.supersedes!r}, expected {old_id!r} — the "
                f"replacement must name what it replaces or the link is lost"
            )
        note = f"supersedes {old_id}: {reason}"
        return self.append(
            Trial(**{**asdict(trial), "date_range": tuple(trial.date_range),
                     "note": f"{trial.note} {note}".strip()})
        )

    # ── integrity ──────────────────────────────────────────────────────────

    def verify_chain(self) -> ChainResult:
        """Recompute the hash chain. Detects edits, deletions and reordering.

        Returns rather than raises: a broken chain is a finding to report, and the caller
        needs the record index to act on it.
        """
        expected = GENESIS
        n = 0
        for i, record in enumerate(self.raw_records()):
            n = i + 1
            found = record.get("prev_hash")
            if found != expected:
                return ChainResult(
                    ok=False, n_records=n, broken_at=i,
                    detail=(f"record {i} (trial_id "
                            f"{record.get('trial_id', '?')!r}) has prev_hash "
                            f"{str(found)[:12]!r}, expected {expected[:12]!r} — a record "
                            f"at or before this point was edited, deleted or reordered"),
                )
            expected = record_hash(record)
        return ChainResult(ok=True, n_records=n, detail=f"{n} records, chain intact")
