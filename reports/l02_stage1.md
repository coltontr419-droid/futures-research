# L02 Stage 1 - opening-range absorption, against matched placebo regions

> **Stage: S7** (multiplicity). Cleared S1-S6; see `reports/STAGES.md` for the
> numbering. This report was written under the retired "Stage 1" label, which maps to
> S6-S8.

**Verdict: null. 0 of 27 cells separate against 1.35 expected by chance.** 27 trials spent;
N 684 -> 711 at this point in the sequence.

Every figure is **(real level) minus (matched placebo region)**, MGC only, **H=180
pre-registered as the sole horizon**, cost floor **0.65 bps**. Trials were logged BEFORE the
run. The condition is sweep-and-reclaim: price exceeds the level by >= m ticks then closes
back inside within k bars, traded **counter to the penetration**.

**The control is weaker than a displaced level** (`decisions.md` 37). It equalises where a
region sits and how often price reaches it, and **nothing about how price arrived**. A
difference here means "behaves differently from an equally-reachable arbitrary region",
which is weaker than "behaves differently given the same approach".

## ABSORPTION ONLY - the sweep arm was withdrawn before this ran

L02 registered two variants on mutually exclusive price paths. **The SWEEP arm was withdrawn
2026-09-11 as degenerate** (`decisions.md` 41): `confirmed_break` fired on every
opening-range level at `valid_from + (k-1)`, so k was an offset rather than a selection, and
the high and low of the same session fired at the same minute in 92-99% of cases. Because the
arms are mutually exclusive by registration, absorption stands alone coherently. A corrected
sweep is a **new registration competing on its own merits**, not an inherited slot.

## WHAT THIS RUN CANNOT ESTABLISH - written before it ran

`decisions.md` 42, recorded while the outcome was unknown:

**L02's registered mechanism is the equity cash open at 09:30 ET. Gold's equivalent is the
COMEX open at 08:20.** On MGC this tests cross-asset spillover, not the registered mechanism,
and it is attenuated exactly as F06 was. MNQ - where the mechanism lives - is unavailable for
an unrelated reason: its best cell fires 5,178 times against a 5,884 detection floor.

**So this null is WEAK evidence against the registered claim.** It closes the only resolvable
route; it does not refute the mechanism, which was never properly exposed. That asymmetry was
stated in advance precisely so it could not be adjusted afterwards.

## Results

Range **-0.623 to +1.836 bps**. Best cell `or60 m=2 k=2` at
**+1.836 bps, p=0.1115** - nominally positive, not separated.

| level type | m | k | n | real | placebo | diff | CI | p | sep |
|---|---|---|---|---|---|---|---|---|---|
| or60 | 2 | 2 | 2,259 | -1.518 | -3.355 | **+1.836** | [-0.30, +4.03] | 0.1115 | - |
| or60 | 4 | 2 | 2,040 | -1.535 | -3.347 | **+1.811** | [-0.62, +4.57] | 0.1625 | - |
| or60 | 8 | 3 | 1,620 | -1.489 | -3.270 | **+1.781** | [-1.14, +4.65] | 0.2515 | - |
| or60 | 8 | 2 | 1,401 | -1.162 | -2.910 | **+1.748** | [-1.69, +5.23] | 0.3305 | - |
| or60 | 2 | 5 | 2,315 | -1.359 | -2.985 | **+1.625** | [-0.51, +3.78] | 0.1690 | - |
| or60 | 4 | 3 | 2,157 | -1.785 | -3.403 | **+1.618** | [-0.70, +4.04] | 0.1750 | - |
| or60 | 2 | 3 | 2,293 | -1.713 | -3.270 | **+1.557** | [-0.57, +3.89] | 0.1875 | - |
| or60 | 8 | 5 | 1,869 | -1.429 | -2.880 | **+1.451** | [-1.08, +4.02] | 0.2875 | - |
| or60 | 4 | 5 | 2,250 | -1.708 | -2.578 | **+0.870** | [-1.36, +3.00] | 0.4535 | - |
| or30 | 8 | 5 | 2,850 | -2.056 | -2.718 | **+0.662** | [-1.33, +2.70] | 0.5570 | - |
| or30 | 2 | 2 | 3,357 | -1.486 | -1.972 | **+0.486** | [-1.39, +2.31] | 0.6025 | - |
| or30 | 2 | 5 | 3,410 | -1.507 | -1.953 | **+0.446** | [-1.30, +2.19] | 0.6400 | - |
| or30 | 2 | 3 | 3,393 | -1.628 | -2.022 | **+0.394** | [-1.34, +2.10] | 0.6630 | - |
| or15 | 8 | 3 | 3,343 | -2.909 | -3.095 | **+0.186** | [-1.86, +2.33] | 0.8595 | - |
| or30 | 4 | 5 | 3,324 | -1.850 | -1.992 | **+0.142** | [-1.58, +1.91] | 0.8835 | - |
| or15 | 8 | 2 | 2,895 | -2.155 | -2.200 | **+0.045** | [-2.21, +2.40] | 0.9690 | - |
| or15 | 4 | 5 | 4,295 | -2.634 | -2.654 | **+0.020** | [-1.56, +1.65] | 0.9795 | - |
| or30 | 8 | 2 | 2,185 | -2.120 | -2.132 | **+0.013** | [-2.54, +2.78] | 0.9905 | - |
| or15 | 4 | 2 | 4,029 | -2.504 | -2.495 | **-0.009** | [-1.70, +1.79] | 0.9915 | - |
| or15 | 2 | 5 | 4,397 | -2.473 | -2.457 | **-0.016** | [-1.61, +1.66] | 0.9855 | - |
| or15 | 2 | 3 | 4,376 | -2.471 | -2.442 | **-0.029** | [-1.65, +1.60] | 0.9775 | - |
| or15 | 2 | 2 | 4,323 | -2.336 | -2.240 | **-0.096** | [-1.78, +1.50] | 0.9050 | - |
| or15 | 8 | 5 | 3,732 | -2.594 | -2.489 | **-0.105** | [-1.88, +1.82] | 0.9125 | - |
| or15 | 4 | 3 | 4,186 | -2.837 | -2.730 | **-0.108** | [-1.79, +1.63] | 0.8995 | - |
| or30 | 4 | 3 | 3,218 | -1.897 | -1.719 | **-0.178** | [-2.07, +1.71] | 0.8500 | - |
| or30 | 4 | 2 | 3,086 | -1.978 | -1.652 | **-0.326** | [-2.29, +1.71] | 0.7460 | - |
| or30 | 8 | 3 | 2,539 | -2.623 | -2.000 | **-0.623** | [-2.78, +1.71] | 0.6040 | - |

## Reading

**Nothing separates.** Zero of 27 against 1.35 expected is below chance, not above it. No BH
correction is needed because no cell reached the conjunctive gate.

Events run 2,259-5,769 per cell against a 2,862 floor at 180m, so the cells that cleared the
floor had adequate power and the reading is a **result rather than an absence of one**.

**Status: retired.** Null on its only resolvable route, with the mechanism caveat above
carried into the registry entry rather than dropped.
