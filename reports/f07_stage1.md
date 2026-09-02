# F07 - gold_session_specific_momentum, Stage 1

Run by `python -m futuresres.signals.f07`. CLAUDE_FUTURES.md §5 Stage 1, §6.

## Nothing below is evidence

Under the corrected detectability gate (`reports/detectability.md`, `reports/decisions.md` §13) **F07 has no route to a verdict at any level, on either instrument.** Every figure in this report is descriptive.

| level | usable events | smallest sample that resolved a floor | status |
|---|---|---|---|
| MGC per cell | ~3,980 | 19,722 | **BELOW SWEPT RANGE** |
| MNQ per cell | ~3,559 | 19,722 | **BELOW SWEPT RANGE** |
| MGC aggregate | ~3,980 | 19,722 | **BELOW SWEPT RANGE** |
| MNQ aggregate | ~3,559 | 19,722 | **BELOW SWEPT RANGE** |

### Why the aggregate does not rescue it, when it rescues F03

A scan whose cells are individually underpowered can usually pool them. F03's 13 half-hour slots are **disjoint trades** - 09:30-10:00 is a different window from 10:00-10:30 - so its pooled series really does hold 13x the observations, and its aggregate is powered even though no single cell is.

F07 cannot do this. Its 12 slots are **twelve predictors of one target**: the catalog regresses the LAST half-hour on each of the first twelve, so every cell enters on the same 15:30 minute of the same session. Pooling stacks twelve correlated readings of one ~4,000-session sample rather than accumulating 48,000 independent ones. Counting that overlap as sample would repeat, one level up, exactly the error the gate was just corrected for.

### What it cost to learn that

**72 trials.** The looks happened, so they enter N and raise SR* for every hypothesis still untested. Recording the cost is the point; declining to log it would be the dishonest option.

## Data

| instrument | sessions | 09:30-17:10 ET minutes traded |
|---|---|---|
| MGC | 3,980 | **67.38%** |
| MNQ | 3,559 | **91.96%** |

The standing MGC caveat (CLAUDE_FUTURES.md §3) applies as always: forward-filling inserts zero returns and biases toward apparent significance. Here it changes nothing, because no MGC number is being read as evidence in the first place.

## MGC - descriptive only

| | |
|---|---|
| cells | 36 (all uninformative) |
| nominal separations | 0 |
| expected by chance at alpha=0.05 | 1.8 |
| BH survivors at FDR 0.05 | 0 |
| smallest p | 0.2006 |

| hold | cells | events | aggregate bps | net bps | best cell | best slot |
|---|---|---|---|---|---|---|
| 30m | 12 | 3,823 | +0.00 | **-0.65** | +0.22 | 10:30-11:00 |
| 60m | 12 | 3,823 | -0.03 | **-0.68** | +0.43 | 12:00-12:30 |
| 90m | 12 | 3,823 | +0.03 | **-0.62** | +0.68 | 10:30-11:00 |
| **ALL** | 36 | | **-0.00** | **-0.65** | +0.68 | 10:30-11:00 |

Best cell +0.68 bps at 10:30-11:00, hold 90m. **No floor is quoted against it**, because no floor was resolved at this sample size - that is what BELOW SWEPT RANGE means. Quoting a ratio here would invent the denominator.

## MNQ - descriptive only

| | |
|---|---|
| cells | 36 (all uninformative) |
| nominal separations | 0 |
| expected by chance at alpha=0.05 | 1.8 |
| BH survivors at FDR 0.05 | 0 |
| smallest p | 0.0503 |

| hold | cells | events | aggregate bps | net bps | best cell | best slot |
|---|---|---|---|---|---|---|
| 30m | 12 | 3,545 | +0.01 | **-0.47** | +1.13 | 11:30-12:00 |
| 60m | 12 | 3,545 | +0.12 | **-0.36** | +1.75 | 11:30-12:00 |
| 90m | 12 | 3,545 | +0.15 | **-0.33** | +2.17 | 11:30-12:00 |
| **ALL** | 36 | | **+0.09** | **-0.39** | +2.17 | 11:30-12:00 |

Best cell +2.17 bps at 11:30-12:00, hold 90m. **No floor is quoted against it**, because no floor was resolved at this sample size - that is what BELOW SWEPT RANGE means. Quoting a ratio here would invent the denominator.

## The redesign that would make F07 testable

Enter at the **close of slot s** and hold h minutes, instead of always entering at 15:30. That makes the 12 positions disjoint, restores a ~48,000-event aggregate, and moves F07 from unresolvable to resolvable at the aggregate level.

It is **a different hypothesis from the catalog's**. The catalog's F07 is specifically the Gao-style claim that gold's session has a different *anchor slot* for the last-half-hour move than equities do; the redesign tests whether slot-by-slot momentum exists at all. Running it would require registering it as its own entry with its own pre-committed grid, and it would carry its own trial cost.
