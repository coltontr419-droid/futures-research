"""Staged two-symbol Stage 1 runs. CLAUDE.md §5 Stage 1 and Stage 4, §6.

WHY STAGED. §5 Stage 4 requires a confirming set of at least two instruments including one
of SOL or XRP. It does NOT require four. Running two first and expanding only for cells
that separate halves the trial cost of every hypothesis that dies — and on the evidence so
far most of them die. The trials saved are not trials avoided by cutting corners: a cell
that separates on neither staged symbol has already told us what four symbols would.

WHY BTC AND SOL AS THE FIRST PAIR. SOL is the least correlated available diversifier
(ρ = 0.647 hourly against BTC, versus ETH's 0.835), so the pair carries more independent
information than BTC+ETH would, and it satisfies the Stage 4 requirement on its own.

EXPANSION RULE: a cell expands if it separates on AT LEAST ONE staged symbol. Not both —
the S04 pattern was BTC separating positive while another instrument separated NEGATIVE,
and requiring agreement before expanding would have hidden exactly the disagreement that
retired it.

EVERY CELL IS LOGGED AT EVERY STAGE, pass or fail (§6). Staging changes which trials are
run, never which are counted.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Final, Sequence

import numpy as np

from futuresres.signals.stage1 import Stage1Result, evaluate_signed_signal
from futuresres.stats.dsr import sharpe_ratio
from futuresres.stats.trials import Trial, TrialLog

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
TRIALS: Final[Path] = ROOT / "trials.jsonl"

STAGE_SYMBOLS: Final[tuple[str, ...]] = ("BTCUSDT", "SOLUSDT")
EXPAND_SYMBOLS: Final[tuple[str, ...]] = ("ETHUSDT", "XRPUSDT")


@dataclass(frozen=True, slots=True)
class Cell:
    """One grid cell: its parameters, its hold, and a name for the log."""

    params: dict
    horizon: int          # hold in minutes

    @property
    def name(self) -> str:
        return "_".join(f"{k}{v}" for k, v in self.params.items())


@dataclass(frozen=True, slots=True)
class CellResult:
    cell: Cell
    symbol: str
    events: int
    mean_bps: float
    sharpe: float
    result: Stage1Result | None
    passed: bool
    reason: str


def evaluate_cell(
    logp: np.ndarray,
    signal: np.ndarray,
    direction: np.ndarray,
    cell: Cell,
    symbol: str,
    rng: np.random.Generator,
    step_minutes: int = 1,
    n_bootstrap: int = 2000,
) -> CellResult:
    """Stage 1 on one cell, evaluated on the SIGNED return so direction is scored.

    An unsigned test would let a signal that correctly predicts DOWN cancel against the
    cases it predicts UP, and report no separation for a signal that works perfectly.

    SCORED AGAINST THE SIGNAL'S OWN EXPOSURE, 2026-08-27. This previously built a return
    series with off-event bars oriented LONG and handed it to `evaluate_signal`, whose
    unconditional baseline is then the asset's long-only drift — while the observed
    statistic is the signal's long/short mix. The gap between those exposures is the
    asset's drift, so a market-neutral signal was charged for drift it never earns, in the
    NEGATIVE direction during a rising sample. Measured on S09/SOL pct20 k1.5 h60:
    +4.76 bps per event reported as +2.34 bps, p 0.0135 reported as 0.2050.
    `evaluate_signed_signal` rotates the signed indicator against the raw forward return
    instead, which is exactly drift-invariant. See tests/test_signed_stage1.py.
    """
    steps = max(cell.horizon // step_minutes, 1)
    idx = np.flatnonzero(signal)
    idx = idx[idx + steps < logp.size]
    per_event = (direction[idx] * (logp[idx + steps] - logp[idx])
                 if idx.size else np.array([]))
    sharpe = (float(sharpe_ratio(per_event))
              if per_event.size >= 2 and per_event.std(ddof=1) > 0 else 0.0)

    res: Stage1Result | None = None
    reason = ""
    if idx.size >= 2:
        try:
            res = evaluate_signed_signal(direction, logp, steps, rng=rng,
                                         n_bootstrap=n_bootstrap)
            reason = res.reason
        except ValueError as exc:
            reason = str(exc)
    else:
        reason = f"only {idx.size} events"

    return CellResult(
        cell=cell, symbol=symbol, events=int(idx.size),
        mean_bps=float(per_event.mean() * 1e4) if per_event.size else 0.0,
        sharpe=sharpe, result=res, passed=bool(res and res.separated), reason=reason,
    )


def _ascii_safe_stdout() -> None:
    """Console encoding must never be able to lose a completed run.

    The S09 run computed and logged all 54 cells, then died printing the summary: a U+2212
    minus sign has no cp1252 mapping, which is what a piped stdout defaults to on Windows.
    Nothing was lost because the trial log is written as each cell finishes, but the
    traceback made a clean null look like a crash. Reconfiguring once here covers every
    hypothesis runner instead of leaving each one to rediscover it.
    """
    stream = getattr(sys, "stdout", None)
    if stream is not None and hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):        # already detached, or not a real stream
            pass


def run_staged(
    hypothesis_id: str,
    cells: Sequence[Cell],
    load: Callable[[str], tuple],
    build_signal: Callable[[tuple, Cell], tuple[np.ndarray, np.ndarray]],
    *,
    rng: np.random.Generator,
    log: TrialLog | None,
    step_minutes: int = 1,
    n_bootstrap: int = 2000,
) -> dict[str, list[CellResult]]:
    """Stage 1 on the staged pair, then expand only what separated.

    `load(symbol)` returns whatever `build_signal` needs, with `logp` as its LAST element.
    """
    _ascii_safe_stdout()
    results: dict[str, list[CellResult]] = {}
    expand: set[str] = set()

    def do_symbol(symbol: str, subset: Sequence[Cell]) -> list[CellResult]:
        data = load(symbol)
        logp = data[-1]
        span = (str(data[0][0])[:10], str(data[0][-1])[:10])
        out: list[CellResult] = []
        for cell in subset:
            signal, direction = build_signal(data, cell)
            r = evaluate_cell(logp, signal, direction, cell, symbol, rng,
                              step_minutes, n_bootstrap)
            out.append(r)
            if log is not None:
                log.append(Trial(
                    trial_id=log.next_id(), hypothesis_id=hypothesis_id,
                    params={**cell.params, "hold_minutes": cell.horizon},
                    symbol=symbol, date_range=span, status="completed",
                    sharpe=r.sharpe, trade_count=r.events,
                    note=("stage1 pass" if r.passed
                          else f"stage1 fail: {r.reason}")[:200],
                ))
            flag = "PASS" if r.passed else "  · "
            print(f"  {flag} {cell.name:<22} events {r.events:>5}  "
                  f"mean {r.mean_bps:>+8.2f} bps  sharpe {r.sharpe:>+8.4f}  "
                  + (f"p={r.result.p_value:.4f}" if r.result else r.reason[:34]))
        return out

    for symbol in STAGE_SYMBOLS:
        print(f"\n=== {symbol} (staged) ===")
        results[symbol] = do_symbol(symbol, cells)
        expand |= {r.cell.name for r in results[symbol] if r.passed}

    if not expand:
        print(f"\nNo cell separated on either staged symbol -- "
              f"{len(EXPAND_SYMBOLS)} x {len(cells)} = "
              f"{len(EXPAND_SYMBOLS) * len(cells)} trials NOT spent.")
        print("S5 Stage 1: no separation at the signal level -- STOP.")
        return results

    subset = [c for c in cells if c.name in expand]
    print(f"\n{len(subset)} of {len(cells)} cells separated on a staged symbol -- "
          f"expanding those to {', '.join(EXPAND_SYMBOLS)}")
    print(f"({len(EXPAND_SYMBOLS) * (len(cells) - len(subset))} trials not spent on the "
          f"cells that did not)")
    for symbol in EXPAND_SYMBOLS:
        print(f"\n=== {symbol} (expansion) ===")
        results[symbol] = do_symbol(symbol, subset)
    return results


def summarise(results: dict[str, list[CellResult]]) -> None:
    """Cross-instrument view — the thing that retired both hypotheses so far."""
    print(f"\n{'=' * 74}")
    print(f"{'symbol':<10} {'cells':>6} {'pass':>5} {'pass pos':>7} {'pass neg':>7} "
          f"{'sharpe range':>22}")
    print("-" * 74)
    for symbol, rows in results.items():
        p = [r for r in rows if r.passed]
        pos = sum(1 for r in p if r.sharpe > 0)
        neg = len(p) - pos
        lo = min((r.sharpe for r in rows), default=0.0)
        hi = max((r.sharpe for r in rows), default=0.0)
        print(f"{symbol:<10} {len(rows):>6} {len(p):>5} {pos:>7} {neg:>7} "
              f"{f'{lo:+.4f} ... {hi:+.4f}':>22}")

    signs = {
        s: ("+" if min(r.sharpe for r in rows) >= 0
            else "-" if max(r.sharpe for r in rows) <= 0 else "±")
        for s, rows in results.items() if rows
    }
    print(f"\nsign by symbol: " + "  ".join(f"{s}={v}" for s, v in signs.items()))
    if len({v for v in signs.values() if v in "+-"}) > 1:
        print("INSTRUMENTS DISAGREE IN SIGN — §5 Stage 4 treats that as strong evidence "
              "against.")
