"""Candidate negative controls, measured but NOT registered. CLAUDE_FUTURES.md §7.

    python -m futuresres.reporting.control_candidates

WHY THE CATALOG NEEDS A NEW CONTROL. `reports/firing_rates.md` showed F10 reaching 1,585 to
5,594 independent events against a swept range starting at 19,722: **the negative control
cannot resolve at any cell on either instrument**. An unpowered control coming back empty
looks exactly like a powered one working correctly, so the catalog currently cannot
demonstrate that its own harness declines to promote noise on real data.

This module measures candidates' firing rates so a replacement can be chosen on evidence.
It computes NO return series, NO statistic and NO p-value, and it registers nothing. Nothing
here spends a trial.

WHAT A NEGATIVE CONTROL HAS TO BE. Three requirements, and the existing pair fails on
different ones.

  1. HIGH ENOUGH FIRING RATE to clear the swept range - on MNQ that means roughly five
     firings a session, because a once-a-session condition tops out near 4,100 events.
  2. NO PLAUSIBLE MECHANISM. Not "an effect that should have been arbitraged away" - that is
     a prediction about the market, and if it is wrong the control is silently a hypothesis.
     It must be a signal that CANNOT relate to future returns by construction.
  3. PARAMETERS FIXED A PRIORI, never swept, so the control cannot be tuned into passing or
     failing.

THE DESIGN THAT IS DELIBERATELY REJECTED. A smooth periodic direction such as
`sign(sin(t/500))` fires every bar and looks attractive on requirement 1. It is rejected on
requirement 2: a periodic signal beats against the session cycle, so it can pick up genuine
time-of-day structure and would then be detecting a real effect rather than nothing. That
exact construction is the §7 POSITIVE control, where its ability to imprint a detectable
pattern is the point. The property that makes it a good positive control is what disqualifies
it as a negative one.

WHAT IS MEASURED HERE INSTEAD. Directions that are deterministic functions of the CLOCK or of
a fixed irrational constant, never of price:

  hash     SHA-256 of the bar's ISO timestamp, low bit -> long/short. Deterministic and
           reproducible across processes, aperiodic, and independent of the date's position
           in the session, so it cannot align with time-of-day.
  pi       successive digits of pi, even -> long, odd -> short. Aperiodic by construction.

each at three firing regimes, because the regime is the whole question:

  slot     every 30-minute RTH slot open - matches F03's regime. Measures 7.9-9.2 a
           session rather than the 13 the slot count implies, because a slot fires only
           when a bar exists at that exact minute.
  session  once a session at 10:00 ET, 1 a session - matches F01/F02/F04/F06/F09's regime
  bar      every bar - matches F11's continuous-exposure regime
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

from futuresres.reporting.firing_rates import (
    SMALLEST_RESOLVING,
    cap_independent,
    load_1m,
    proxy_horizon,
    span_minutes,
)

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
REPORT: Final[Path] = ROOT / "reports" / "control_candidates.md"
CACHE: Final[Path] = ROOT / "reports" / "control_candidates.json"

RTH_START: Final[int] = 9 * 60 + 30
RTH_END: Final[int] = 16 * 60
SLOT_MINUTES: Final[int] = 30
SESSION_MINUTE: Final[int] = 10 * 60          # 10:00 ET
HOLDS: Final[tuple[int, ...]] = (30, 60, 120)

#: Only enough digits for the balance sanity check below. The FIRING COUNTS do not depend
#: on the signal at all - they come from the clock mask - so generating hundreds of
#: thousands of digits would buy nothing and the spigot is quadratic in big-integer work.
#: A first attempt at 200,000 did not finish and was killed.
PI_DIGITS_NEEDED: Final[int] = 5_000


def pi_digits(n: int) -> np.ndarray:
    """First `n` digits of pi, by the standard spigot. Fixed a priori and reproducible."""
    digits: list[int] = []
    q, r, t, k, m, x = 1, 0, 1, 1, 3, 3
    while len(digits) < n:
        if 4 * q + r - t < m * t:
            digits.append(m)
            q, r, m = 10 * q, 10 * (r - m * t), (10 * (3 * q + r)) // t - 10 * m
        else:
            q, r, t, k, m, x = (q * k, (2 * q + r) * x, t * x, k + 1,
                                (q * (7 * k + 2) + r * x) // (t * x), x + 2)
    return np.array(digits, dtype=np.int8)


def hash_direction(timestamps: np.ndarray) -> np.ndarray:
    """+1/-1 from SHA-256 of each bar's ISO timestamp. No price input, ever."""
    out = np.empty(timestamps.size, dtype=np.int8)
    for i, ts in enumerate(timestamps):
        h = hashlib.sha256(str(ts).encode("ascii")).digest()
        out[i] = 1 if h[0] & 1 else -1
    return out


@dataclass(slots=True)
class Candidate:
    name: str
    signal: str
    regime: str
    product: str
    horizon: int
    firings: int
    independent: int
    per_session: float
    needs: int
    status: str


def firing_mask(df: pl.DataFrame, regime: str) -> np.ndarray:
    mod = df.get_column("mod").to_numpy()
    if regime == "bar":
        return np.ones(mod.size, dtype=bool)
    if regime == "session":
        return mod == SESSION_MINUTE
    if regime == "slot":
        return ((mod >= RTH_START) & (mod < RTH_END)
                & ((mod - RTH_START) % SLOT_MINUTES == 0))
    raise ValueError(regime)


def measure(products: tuple[str, ...] = ("MNQ", "MGC")) -> list[Candidate]:
    digits = pi_digits(PI_DIGITS_NEEDED)
    out: list[Candidate] = []
    for product in products:
        df = load_1m(product)
        span = span_minutes(df)
        n_sessions = df.get_column("day").n_unique()
        ts = df.get_column("ts_event").to_numpy()
        for regime in ("slot", "session", "bar"):
            mask = firing_mask(df, regime)
            n_fire = int(mask.sum())
            for signal in ("hash", "pi"):
                # The direction is built to prove it is computable and non-degenerate; it
                # is never combined with a return here.
                if signal == "hash":
                    sample = hash_direction(ts[mask][:5_000])
                else:
                    idx = np.arange(min(n_fire, digits.size))
                    sample = np.where(digits[idx] % 2 == 0, 1, -1)
                balance = float(np.mean(sample == 1)) if sample.size else 0.0
                for hold in HOLDS:
                    indep = cap_independent(n_fire, span, hold)
                    need = SMALLEST_RESOLVING.get((product, proxy_horizon(hold)), 0)
                    out.append(Candidate(
                        f"{signal}-{regime}", signal, regime, product, hold,
                        n_fire, indep, n_fire / max(n_sessions, 1), need,
                        "RESOLVABLE" if indep >= need else "BELOW SWEPT RANGE",
                    ))
                if hold == HOLDS[-1]:
                    print(f"  {product} {signal}-{regime}: {n_fire:,} firings, "
                          f"long share {balance:.3f}")
    return out


def render(cands: list[Candidate]) -> str:
    w: list[str] = []
    a = w.append
    a("# Candidate negative controls — measured, not registered")
    a("")
    a("Generated by `python -m futuresres.reporting.control_candidates`. "
      "CLAUDE_FUTURES.md §7; `reports/decisions.md` §17.")
    a("")
    a("**Nothing here is registered and nothing here spends a trial.** No return series, no "
      "statistic, no p-value — only firing rates, so a replacement control can be chosen on "
      "evidence rather than on a guess about how often a condition triggers.")
    a("")

    a("## Why the existing pair cannot serve")
    a("")
    a("| | F10 rsi_mean_reversion_control | F11 ma_crossover_control |")
    a("|---|---|---|")
    a("| firing rate | 1,585–5,594 independent | 43,759–173,879 independent |")
    a("| clears the swept range | **no, at any cell** | yes, everywhere |")
    a("| genuinely mechanism-free | defensible | **no** |")
    a("| verdict | **unpowered** | **not a control** |")
    a("")
    a("**F10 fails on power.** 5,594 events at best against 19,722. An unpowered control "
      "coming back empty is indistinguishable from a powered one working correctly, so it "
      "cannot support the claim it exists to support.")
    a("")
    a("**F11 fails on something worse, and it would have failed even at ten times the "
      "sample.** Its registry entry justifies it as \"the canonical published trend rule "
      "[with] no counterparty story\". That justification is a *prediction about the "
      "market* — that the rule is arbitraged away — and the prediction is contestable. A "
      "fast/slow moving-average crossover is time-series momentum, which in **futures "
      "specifically** is among the best-documented anomalies in the literature (Moskowitz, "
      "Ooi & Pedersen, JFE 2012, across 58 contracts), and the managed-futures industry is "
      "built on it. The usual counterparty story — hedging demand and under-reaction — is "
      "the same family of story F01 in this very catalog relies on.")
    a("")
    a("That is the disqualifying part. **F01 is a momentum hypothesis and F11 is a slow "
      "momentum rule.** If the harness promoted F11, there would be no way to tell a "
      "pipeline failure from a correct detection of a real effect — which is precisely the "
      "distinction a negative control exists to make. The same objection applies in weaker "
      "form to F10 against F02, the reversal hypothesis.")
    a("")
    a("A control's premise must be **\"this cannot relate to future returns by "
      "construction\"**, never **\"this should have been arbitraged away\"**. The second is "
      "a hypothesis wearing a control's label.")
    a("")

    a("## The design deliberately rejected")
    a("")
    a("A smooth periodic direction such as `sign(sin(t/500))` fires every bar and would "
      "clear the sample requirement easily. It is rejected: a periodic signal beats against "
      "the session cycle and can pick up genuine time-of-day structure, at which point it is "
      "detecting a real effect rather than nothing. **That exact construction is the §7 "
      "positive control**, where its ability to imprint a detectable pattern is the whole "
      "point. What makes it a good positive control disqualifies it as a negative one.")
    a("")

    a("## Candidates measured")
    a("")
    a("Two mechanism-free signals, each at three firing regimes. Both are deterministic "
      "functions of the clock or of a fixed constant and **never touch price**:")
    a("")
    a("- **hash** — SHA-256 of the bar's ISO timestamp, low bit → long/short. Reproducible "
      "across processes, aperiodic, and since each date hashes differently it cannot align "
      "with time-of-day.")
    a("- **pi** — successive digits of π, even → long, odd → short. Aperiodic by "
      "construction, fixed a priori in the strongest sense available: it was chosen before "
      "any data was seen and cannot be re-chosen.")
    a("")
    a("| candidate | regime | fires/session | product | hold | independent | needs | status |")
    a("|---|---|---|---|---|---|---|---|")
    for c in sorted(cands, key=lambda c: (c.signal, c.regime, c.product, c.horizon)):
        a(f"| {c.name} | {c.regime} | {c.per_session:.1f} | {c.product} | {c.horizon}m | "
          f"{c.independent:,} | {c.needs:,} | "
          + (f"**{c.status}**" if c.status == "RESOLVABLE" else c.status) + " |")
    a("")

    slot = [c for c in cands if c.regime == "slot"]
    sess = [c for c in cands if c.regime == "session"]
    a("## What the measurements say")
    a("")
    ok_slot = sum(c.status == "RESOLVABLE" for c in slot)
    ok_sess = sum(c.status == "RESOLVABLE" for c in sess)
    a(f"**The 30-minute-slot regime resolves in all {ok_slot} of {len(slot)} combinations.** "
      f"It fires **7.9 times a session on MGC and 9.2 on MNQ** — not the 13 the RTH slot "
      f"count would suggest, because a slot only fires when a bar exists at exactly that "
      f"minute, and holidays, half days and thin minutes remove the rest. That gap between "
      f"the assumed 13 and the measured 9.2 is the reason this module exists: the same "
      f"assumption applied to the detectability gate is what §13 had to correct.")
    a("")
    a("Either signal works; the counts are identical because the firing rate depends only "
      "on the clock mask, not on the direction. **`hash-slot` is the recommendation**, "
      "because a hash is self-documenting — a reader can recompute any single direction "
      "from the timestamp alone and confirm no price entered it.")
    a("")
    a(f"**The once-a-session regime resolves in only {ok_sess} of {len(sess)} "
      f"combinations** — MGC at the 120-minute hold, and nowhere else. It fires 0.7 times a "
      f"session, not 1.0, because 10:00 ET is missing from some sessions entirely. That "
      f"single exception is instructive rather than encouraging: it clears only because "
      f"MGC's floor at the 180-minute proxy resolves at 2,862, the lowest threshold in the "
      f"study, on the instrument carrying the coverage caveat.")
    a("")
    a("> A once-a-session condition on sixteen years yields ~3,500 events against MNQ's "
      "19,722. **No control of any construction can clear the bar on MNQ in the regime "
      "where most of this catalog's hypotheses actually live.** F10's failure was never "
      "about RSI being a poor choice; it was about firing rate, and any replacement that "
      "matched those hypotheses' event regime would fail the same way.")
    a("")
    a("So the replacement control necessarily validates the harness **in a different regime "
      "from the one most hypotheses use**. It demonstrates that the pipeline does not "
      "promote a mechanism-free signal on real futures data at F03-like event counts. It "
      "cannot demonstrate the same at F01-like event counts, because at those counts nothing "
      "is demonstrable — which is itself the reason those hypotheses are blocked. The claim "
      "the control licenses must be stated with that scope attached, not quietly generalised.")
    a("")
    a("The synthetic GARCH nulls in `reports/integrity_futures.md` remain the control for "
      "the harness itself (0/24 promoted at 20,000 bars). What a real-data control adds is "
      "that the result survives actual microstructure — real gaps, real volatility "
      "clustering, real session boundaries — rather than only idealised noise.")
    a("")
    a("## Recommendation, for a decision — nothing is registered")
    a("")
    a("| | |")
    a("|---|---|")
    a("| **register** | `hash-slot` — SHA-256 of the bar timestamp, fired at each 30-minute RTH slot open, holds 30/60/120, both instruments |")
    a("| **retire** | F11 — not a control; it is a momentum rule in a catalog containing a momentum hypothesis |")
    a("| **retire or keep as-is** | F10 — sound premise, but permanently unpowered at its own firing rate |")
    a("")
    a("If `hash-slot` is registered, its parameters are fixed by this document before any "
      "run: SHA-256, low bit, 30-minute RTH slot opens, holds {30, 60, 120}. Recording them "
      "here is what makes \"fixed a priori\" checkable rather than asserted.")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(prog="futuresres.reporting.control_candidates").parse_args(argv)
    cands = measure()
    CACHE.write_text(json.dumps([asdict(c) for c in cands], indent=2), encoding="utf-8")
    REPORT.write_text(render(cands), encoding="utf-8")
    print(f"\nwrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
