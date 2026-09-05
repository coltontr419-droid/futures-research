# F06 - cash_open_drive_continuation, Stage 1

Run by `python -m futuresres.signals.f06`. CLAUDE_FUTURES.md §5, §6, §7.6.

## Read this before any number below

**Both open routes are MGC, and MGC is where this mechanism is weakest.** The mechanism names 09:30 ET as the moment overnight positioning meets CASH liquidity - that is the EQUITY cash open. Gold's own liquidity event is the COMEX open at 08:20 ET. On MGC this condition therefore tests **cross-asset spillover** from the equity open, not the registered claim.

**A positive result here would not support the mechanism as written.** It would say gold moves directionally after the equity cash open - a different proposition with a different counterparty - and promoting it would require re-registration as its own hypothesis with its own pre-committed grid and trial budget. Recorded in the registry before this run, not after seeing it.

**MNQ - where the mechanism actually lives - was NOT RUN.** It is closed on every route at 1,708 measured events against the 19,722 at which a floor resolves. Spending 36 trials there would raise SR\* for the rest of the catalog and buy nothing. **Its absence from this report is a closed route, not a null.**

## What can carry a verdict

| hold | cells | events | resolving threshold | status |
|---|---|---|---|---|
| 60m | 12 | 3,958 | 5,620 | **UNINFORMATIVE** |
| 120m | 12 | 3,952 | 2,862 | informative |
| 180m | 12 | 3,941 | 2,862 | informative |

MGC at 60 minutes is below the swept range and its cells are excluded from the verdict. The 120m and 180m holds map to the 180-minute floor cell, whose threshold of 2,862 is the lowest in the study - these routes are open by the narrowest margin available anywhere in the catalog.

## Multiplicity

| | |
|---|---|
| informative cells | 12 of 36 |
| **nominal separations** | **0** |
| expected by chance at alpha=0.05 | 0.60 |
| **BH survivors at FDR 0.05** | **0** |
| smallest p | 0.2461 |

The cells overlap heavily - the three holds share entry minutes, and W and confirm select nested subsets of the same breakouts - so effective independent looks are fewer than the cell count and expected-by-chance is an overestimate.

## Effect against the detection floor

| hold | cells | events | aggregate bps | net | best cell | floor | best/floor |
|---|---|---|---|---|---|---|---|
| 60m (uninformative) | 12 | 3,958 | +0.75 | **+0.10** | +2.33 | 4.17 | 0.56x |
| 120m | 12 | 3,952 | +0.35 | **-0.30** | +2.59 | 14.34 | 0.18x |
| 180m | 12 | 3,941 | +0.66 | **+0.01** | +2.84 | 14.34 | 0.20x |
| **informative** | 12 | | **-0.62** | **-1.27** | -0.02 | | |

## No real-data control exists at this event regime

F14, the catalog's negative control, fires ~13 times a session and reaches ~48,000-52,000 events. It established that the harness declines to promote a mechanism-free signal **at that sample size**. F06's cells hold ~3,900.

**No control can be built at F06's regime on this data.** It fires once per session, and measured candidates at that regime resolved in only 2 of 12 combinations (`reports/control_candidates.md`) - both MGC at the longest hold, on the instrument carrying the coverage caveat. So this result carries the §7.2 synthetic GARCH assurance and **nothing from F14**.

## Data

| instrument | sessions | 09:30-15:55 ET minutes traded |
|---|---|---|
| MGC | 3,980 | 70.88% |

Breakouts whose full hold would not fit before 15:55 ET are excluded rather than truncated - a shortened hold is a different holding period, and §2's 17:00 hard exit requires the same of a real position. At most 133 sessions were excluded that way, at H=3h where entry must occur by 12:55.

## Every cell

| W | confirm | vol_filter | hold | events | mean bps | Sharpe | p | |
|---|---|---|---|---|---|---|---|---|
| 5 | 1 | >median | 60m | 1,956 | +1.43 | +0.0299 | 0.1020 | UNINFORMATIVE |
| 5 | 1 | >median | 120m | 1,953 | +0.98 | +0.0170 | 0.3730 | UNINFORMATIVE |
| 5 | 1 | >median | 180m | 1,950 | +1.68 | +0.0262 | 0.2631 | UNINFORMATIVE |
| 5 | 1 | none | 60m | 3,958 | -0.37 | -0.0096 | 0.4644 | UNINFORMATIVE |
| 5 | 1 | none | 120m | 3,952 | -0.84 | -0.0183 | 0.3163 |  |
| 5 | 1 | none | 180m | 3,941 | -0.54 | -0.0105 | 0.6396 |  |
| 5 | 2 | >median | 60m | 1,955 | +1.52 | +0.0322 | 0.0916 | UNINFORMATIVE |
| 5 | 2 | >median | 120m | 1,952 | +0.83 | +0.0146 | 0.4400 | UNINFORMATIVE |
| 5 | 2 | >median | 180m | 1,948 | +1.99 | +0.0314 | 0.1933 | UNINFORMATIVE |
| 5 | 2 | none | 60m | 3,957 | -0.50 | -0.0133 | 0.3365 | UNINFORMATIVE |
| 5 | 2 | none | 120m | 3,950 | -1.01 | -0.0224 | 0.2461 |  |
| 5 | 2 | none | 180m | 3,939 | -0.51 | -0.0101 | 0.6569 |  |
| 15 | 1 | >median | 60m | 1,949 | +2.33 | +0.0519 | 0.0312 | UNINFORMATIVE |
| 15 | 1 | >median | 120m | 1,942 | +2.59 | +0.0489 | 0.0573 | UNINFORMATIVE |
| 15 | 1 | >median | 180m | 1,934 | +2.84 | +0.0465 | 0.0776 | UNINFORMATIVE |
| 15 | 1 | none | 60m | 3,944 | +0.16 | +0.0046 | 0.7411 | UNINFORMATIVE |
| 15 | 1 | none | 120m | 3,929 | -0.02 | -0.0004 | 0.9821 |  |
| 15 | 1 | none | 180m | 3,910 | -0.10 | -0.0021 | 0.9253 |  |
| 15 | 2 | >median | 60m | 1,947 | +2.18 | +0.0498 | 0.0381 | UNINFORMATIVE |
| 15 | 2 | >median | 120m | 1,937 | +1.76 | +0.0336 | 0.1590 | UNINFORMATIVE |
| 15 | 2 | >median | 180m | 1,924 | +2.12 | +0.0351 | 0.1755 | UNINFORMATIVE |
| 15 | 2 | none | 60m | 3,939 | -0.21 | -0.0060 | 0.6746 | UNINFORMATIVE |
| 15 | 2 | none | 120m | 3,920 | -0.50 | -0.0120 | 0.5347 |  |
| 15 | 2 | none | 180m | 3,893 | -0.50 | -0.0105 | 0.6464 |  |
| 30 | 1 | >median | 60m | 1,907 | +1.95 | +0.0469 | 0.0517 | UNINFORMATIVE |
| 30 | 1 | >median | 120m | 1,888 | +1.32 | +0.0264 | 0.2701 | UNINFORMATIVE |
| 30 | 1 | >median | 180m | 1,865 | +1.71 | +0.0300 | 0.2706 | UNINFORMATIVE |
| 30 | 1 | none | 60m | 3,859 | -0.40 | -0.0122 | 0.4539 | UNINFORMATIVE |
| 30 | 1 | none | 120m | 3,829 | -0.65 | -0.0162 | 0.4427 |  |
| 30 | 1 | none | 180m | 3,772 | -0.77 | -0.0170 | 0.4896 |  |
| 30 | 2 | >median | 60m | 1,889 | +1.48 | +0.0366 | 0.1008 | UNINFORMATIVE |
| 30 | 2 | >median | 120m | 1,867 | +0.64 | +0.0131 | 0.5631 | UNINFORMATIVE |
| 30 | 2 | >median | 180m | 1,833 | +1.07 | +0.0191 | 0.4743 | UNINFORMATIVE |
| 30 | 2 | none | 60m | 3,822 | -0.63 | -0.0197 | 0.2697 | UNINFORMATIVE |
| 30 | 2 | none | 120m | 3,784 | -0.94 | -0.0242 | 0.2789 |  |
| 30 | 2 | none | 180m | 3,713 | -1.07 | -0.0240 | 0.3434 |  |

**36 trials**, MGC only. 3 W x 2 confirm x 2 vol_filter x 3 holds.
