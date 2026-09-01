# F04 - lbma_auction_flow, Stage 1

Run by `python -m futuresres.signals.f04`. CLAUDE_FUTURES.md section 5 Stage 1, 6.

- **Grid:** 2 auctions x 3 pre-windows x 3 holds = 18 cells per instrument, 36 total
- **Direction:** reversion, the direction the mechanism predicts. Continuation is its exact sign flip - same p-value, negated mean - so running both would double the trial count and buy nothing.

## The auctions are converted, not offset

| | normal weeks | DST divergence weeks |
|---|---|---|
| AM (10:30 London) | 05:30 ET | **06:30 ET** |
| PM (15:00 London) | 10:00 ET | **11:00 ET** |

Europe and the US shift on different dates, so for roughly four weeks a year - about 8% of observations - a fixed ET offset would place every auction an hour wrong, in a hypothesis whose whole content is what happens at one specific minute. The conversion runs through `session.calendar`.

## Which combinations can carry a verdict

| instrument | hold | usable events | status |
|---|---|---|---|
| MGC | 30m | 3,880 | informative |
| MGC | 60m | 3,880 | informative |
| MGC | 120m | 3,880 | informative |
| MNQ | 30m | 3,554 | **UNINFORMATIVE** - below the swept range |
| MNQ | 60m | 3,554 | **UNINFORMATIVE** - below the swept range |
| MNQ | 120m | 3,554 | informative |

**MNQ at 30 and 60 minutes cannot support a null.** The condition fires twice a business day, reaching ~8,250 events against the 19,722 at which a floor first resolves for MNQ at that horizon (`reports/detectability.md`). Those six cells are reported below for completeness and are **excluded from every verdict**: a null there is the absence of evidence, not evidence of absence.

**MGC is unblocked across its whole range, and is where the mechanism lives.** The LBMA fixes the price of gold. MNQ is included because the catalog lists it, not because anyone expects a London gold auction to move the Nasdaq - it functions as a control on the confound rather than as a second test of the mechanism.

## Data caveat - the standing MGC one

| instrument | sessions | 04:00-14:00 ET minutes traded |
|---|---|---|
| MGC | 3,992 | **70.47%** |
| MNQ | 3,567 | **99.13%** |

Per the standing caveat in CLAUDE_FUTURES.md section 3, MGC's thin tape means nearly three minutes in ten are carried forward rather than traded. Forward-filling inserts zero returns, thinning measured volatility and biasing toward apparent significance - so **an MGC null is weaker evidence than the same null on MNQ**. That matters directly here, because MGC is the instrument that would have to carry a positive verdict.

## MGC

### Multiplicity

| | |
|---|---|
| informative cells | 18 of 18 (0 excluded as uninformative) |
| **nominal separations** | **2** |
| expected by chance at alpha=0.05 | **0.9** |
| **BH survivors at FDR 0.05** | **0** |
| smallest p | 0.0341 (BH rank-1 threshold 0.002778) |

### Effect against the detection floor

Cost floor **0.65 bps**.

| hold | cells | events | aggregate bps | net bps | best cell | floor bps | best vs floor |
|---|---|---|---|---|---|---|---|
| 30m | 6 | 3,880 | +0.34 | **-0.31** | +0.93 | 5.46 | 0.17x |
| 60m | 6 | 3,880 | +0.51 | **-0.14** | +1.25 | 4.17 | 0.30x |
| 120m | 6 | 3,880 | +0.55 | **-0.10** | +1.04 | 11.70 | 0.09x |
| **ALL informative** | 18 | | **+0.47** | **-0.18** | +1.25 | | |

**Aggregate across the 18 informative cells: +0.47 bps gross, -0.18 net.** Best single cell +1.25 gross. The floor column uses the measured multiple from the nearest swept horizon times this hold's own sigma, so it is an estimate at 30 and 120 minutes where no floor was swept directly.

## MNQ

### Multiplicity

| | |
|---|---|
| informative cells | 6 of 18 (12 excluded as uninformative) |
| **nominal separations** | **0** |
| expected by chance at alpha=0.05 | **0.3** |
| **BH survivors at FDR 0.05** | **0** |
| smallest p | 0.2398 (BH rank-1 threshold 0.008333) |

### Effect against the detection floor

Cost floor **0.48 bps**.

| hold | cells | events | aggregate bps | net bps | best cell | floor bps | best vs floor |
|---|---|---|---|---|---|---|---|
| 30m (uninformative) | 6 | 3,554 | -0.33 | **-0.81** | +0.10 | not measured | — |
| 60m (uninformative) | 6 | 3,554 | +0.01 | **-0.47** | +0.48 | not measured | — |
| 120m | 6 | 3,554 | -0.31 | **-0.79** | +0.47 | 12.90 | 0.04x |
| **ALL informative** | 6 | | **-0.31** | **-0.79** | +0.47 | | |

**Aggregate across the 6 informative cells: -0.31 bps gross, -0.79 net.** Best single cell +0.47 gross. The floor column uses the measured multiple from the nearest swept horizon times this hold's own sigma, so it is an estimate at 30 and 120 minutes where no floor was swept directly.
