# F03 - half_hour_periodicity, Stage 1

Run by `python -m futuresres.signals.f03`. CLAUDE_FUTURES.md section 5 Stage 1, 6.

- **Grid:** 13 RTH slots x 3 lookbacks x 3 thresholds = 117 cells per instrument, 234 total
- **Instruments:** MNQ (spliced NQ+MNQ) and MGC
- **Horizon:** 30 minutes. Entry at the slot open, exit at the slot close, so the trade return IS that slot's return that day - a time exit, per section 9

## The threshold reading - a decision

The catalog writes the threshold as "x slot sigma" but also requires a significant trailing t-stat. Read literally, the first clause compares a mean of N days against a ONE-DAY sigma: at N=40, threshold=1.5 that demands 9.5 standard errors. Measured across all 13 slots and all nine (N, threshold) cells:

| reading | min events | median | max |
|---|---|---|---|
| literal, mean vs `threshold * sigma` | 0 | **40** | 6,818 |
| t-stat, mean vs `threshold * sigma/sqrt(N)` | 5,756 | **14,818** | 29,465 |

**The literal reading is vacuous** - 40 events across 13 slots and ~3,500 sessions is not a testable hypothesis, and it renders the t-stat clause redundant. The **t-stat reading** is used below.

## Data caveat

| instrument | sessions | RTH minutes actually traded |
|---|---|---|
| MGC | 3,980 | **70.85%** |
| MNQ | 3,559 | **98.31%** |

The RTH grid is reindexed to exactly 390 minutes per session with the last trade carried forward, because the evaluator indexes its forward window by BAR - on a series with untraded minutes, "30 bars" would not be "30 minutes" and every slot boundary would drift.

**MGC trades only ~71% of RTH minutes, so nearly three in ten of its bars are carried rather than traded.** Forward-filling inserts zero returns, which thins measured volatility and can inflate apparent significance. The MGC result below must be read with that in mind. MNQ at 98% needs no such qualification.

## MGC

### Multiplicity

| | |
|---|---|
| cells scored | 117 of 117 |
| **nominal separations** | **0** |
| expected by chance at alpha=0.05 | **5.9** |
| **BH survivors at FDR 0.05** | **0** |
| smallest p | 0.0707 (BH rank-1 threshold 0.000427) |

### Per slot, and the selection check

Cost floor **0.65 bps**; measured detection floor **4.17 bps** (`reports/calibration.md`).

| slot | ET window | events | gross bps | **net bps** | best cell gross | nominal hits |
|---|---|---|---|---|---|---|
| 0 | 09:30-10:00 | 14,053 | +0.48 | **-0.17** | +1.73 | 0 |
| 1 | 10:00-10:30 | 13,691 | +0.87 | **+0.22** | +1.49 | 0 |
| 2 | 10:30-11:00 | 12,507 | -0.98 | **-1.63** | +0.20 | 0 |
| 3 | 11:00-11:30 | 12,826 | -0.55 | **-1.20** | +0.10 | 0 |
| 4 | 11:30-12:00 | 13,536 | -0.26 | **-0.91** | +0.26 | 0 |
| 5 | 12:00-12:30 | 14,217 | +0.32 | **-0.33** | +0.76 | 0 |
| 6 | 12:30-13:00 | 13,980 | -0.28 | **-0.93** | +0.20 | 0 |
| 7 | 13:00-13:30 | 13,365 | -0.10 | **-0.75** | +0.23 | 0 |
| 8 | 13:30-14:00 | 13,326 | +0.08 | **-0.57** | +0.57 | 0 |
| 9 | 14:00-14:30 | 13,164 | +0.08 | **-0.57** | +0.53 | 0 |
| 10 | 14:30-15:00 | 14,118 | +0.33 | **-0.32** | +0.91 | 0 |
| 11 | 15:00-15:30 | 12,733 | -0.08 | **-0.73** | +0.25 | 0 |
| 12 | 15:30-16:00 | 14,655 | +0.46 | **-0.19** | +1.15 | 0 |
| **ALL SLOTS** | 09:30-16:00 | 176,171 | **+0.03** | **-0.62** | +1.73 | 0 |

**Aggregate across all 117 cells: +0.03 bps gross, -0.62 net of the 0.65 bps cost floor.** The best single cell reaches +1.73 gross. The gap between those two numbers is the size of the selection effect, and the aggregate is the one nobody chose after the fact.

## MNQ

### Multiplicity

| | |
|---|---|
| cells scored | 117 of 117 |
| **nominal separations** | **8** |
| expected by chance at alpha=0.05 | **5.9** |
| **BH survivors at FDR 0.05** | **0** |
| smallest p | 0.0066 (BH rank-1 threshold 0.000427) |

### Per slot, and the selection check

Cost floor **0.48 bps**; measured detection floor **2.57 bps** (`reports/calibration.md`).

| slot | ET window | events | gross bps | **net bps** | best cell gross | nominal hits |
|---|---|---|---|---|---|---|
| 0 | 09:30-10:00 | 9,593 | -3.42 | **-3.90** | -1.26 | 7 |
| 1 | 10:00-10:30 | 10,696 | -1.59 | **-2.07** | -0.63 | 1 |
| 2 | 10:30-11:00 | 12,009 | +0.15 | **-0.33** | +0.54 | 0 |
| 3 | 11:00-11:30 | 11,464 | -0.34 | **-0.82** | +0.15 | 0 |
| 4 | 11:30-12:00 | 11,347 | -0.35 | **-0.83** | +0.33 | 0 |
| 5 | 12:00-12:30 | 11,045 | +0.16 | **-0.32** | +0.83 | 0 |
| 6 | 12:30-13:00 | 11,922 | -0.32 | **-0.80** | +0.64 | 0 |
| 7 | 13:00-13:30 | 11,629 | -0.21 | **-0.69** | +0.62 | 0 |
| 8 | 13:30-14:00 | 11,835 | +0.66 | **+0.18** | +1.60 | 0 |
| 9 | 14:00-14:30 | 11,976 | -0.46 | **-0.94** | +0.02 | 0 |
| 10 | 14:30-15:00 | 12,372 | -0.06 | **-0.54** | +0.39 | 0 |
| 11 | 15:00-15:30 | 12,183 | +0.09 | **-0.39** | +0.47 | 0 |
| 12 | 15:30-16:00 | 12,284 | -0.34 | **-0.82** | +1.12 | 0 |
| **ALL SLOTS** | 09:30-16:00 | 150,355 | **-0.46** | **-0.94** | +1.60 | 8 |

**Aggregate across all 117 cells: -0.46 bps gross, -0.94 net of the 0.48 bps cost floor.** The best single cell reaches +1.60 gross. The gap between those two numbers is the size of the selection effect, and the aggregate is the one nobody chose after the fact.
