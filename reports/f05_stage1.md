# F05 - volatility_compression_expansion, Stage 1

Run by `python -m futuresres.signals.f05`. CLAUDE_FUTURES.md §5, §6, §7.6.

## The condition that ran is the CORRECTED one

Two specification repairs were adopted and recorded **before** this run - neither a tuning choice, both derived from the mechanism (`reports/decisions.md` §23, §27).

| | registered | corrected | why |
|---|---|---|---|
| break deadline | none | **60 min** | a 1-hour vol estimate forecasts about the next hour, and the compression midpoint goes stale beyond it |
| `k*sigma` reference | the compressed window's own sigma | **trailing-20 median sigma at the same clock hour** | expansion means volatility returning toward NORMAL, so the trigger must reference normal |

The second repair matters most: measuring against the compressed window's own sigma meant compression shrank the trigger distance exactly when the filter fired, so the condition broke on 79-91% of armings and **k did almost nothing**. Under the correction, break rates run 72-78% at k=1.5 and 44-50% at k=2.5.

## What can carry a verdict

| instrument | hold | measured events | status |
|---|---|---|---|
| MGC | 60m | 18,591 | informative |
| MGC | 120m | 17,783 | informative |
| MGC | 180m | 17,029 | informative |
| MNQ | 60m | 15,824 | **UNINFORMATIVE** - below swept range |
| MNQ | 120m | 15,163 | informative |
| MNQ | 180m | 14,473 | informative |

**MNQ at 60 minutes cannot support a null**: 6,965 measured events against the 19,722 at which a floor first resolves. Its nine cells are reported below for completeness and **excluded from every verdict** - a null there is the absence of evidence, not evidence of absence.

## Multiplicity

| instrument | informative cells | nominal | expected by chance | BH survivors |
|---|---|---|---|---|
| MGC | 27 of 27 | 1 | 1.35 | **0** |
| MNQ | 18 of 27 | 0 | 0.90 | **0** |
| **both** | 45 | 1 | 2.25 | **0** |

Benjamini-Hochberg is applied within the hypothesis across its informative cells. Note the cells overlap heavily - the three holds share entry minutes and the three vol_pct settings are nested - so effective independent looks are fewer than the cell count and expected-by-chance is an overestimate.

## Effect against the detection floor

| instrument | hold | cells | events | aggregate bps | net | best cell | floor | best/floor |
|---|---|---|---|---|---|---|---|---|
| MGC | 60m | 9 | 18,591 | -0.33 | **-0.98** | -0.26 | 4.17 | -0.06x |
| MGC | 120m | 9 | 17,783 | -0.17 | **-0.82** | +0.06 | 14.34 | 0.00x |
| MGC | 180m | 9 | 17,029 | -0.18 | **-0.83** | +0.13 | 14.34 | 0.01x |
| **MGC informative** | | 27 | | **-0.23** | **-0.88** | +0.13 | | |
| MNQ | 60m (uninformative) | 9 | 15,824 | -0.07 | **-0.55** | +0.17 | 2.57 | 0.06x |
| MNQ | 120m | 9 | 15,163 | -0.09 | **-0.57** | +0.41 | 15.66 | 0.03x |
| MNQ | 180m | 9 | 14,473 | +0.17 | **-0.31** | +0.79 | 15.66 | 0.05x |
| **MNQ informative** | | 18 | | **+0.04** | **-0.44** | +0.79 | | |

## Which instrument carries a verdict

**Neither instrument separates, and MNQ carries the stronger of the two nulls.**

MNQ's informative cells (120m and 180m) sit on 83.16% coverage. MGC's three holds are all informative but rest on **64.16%** coverage - more than a third of this window's minutes are carried forward rather than traded, the standing caveat from CLAUDE_FUTURES.md §3. Forward-filling inserts zero returns, thins measured volatility and biases toward APPARENT significance, so an MGC null is the weaker kind. Here both point the same way, which is the easy case: the caveat would have mattered had MGC separated and MNQ not.

F05's mechanism - volatility clustering - is generic to speculative price series and holds in both instruments (`mechanism_instruments`), so neither is a control for the other and neither is the wrong instrument for the claim.

## No real-data control exists at this event regime

F14, the catalog's negative control, fires ~13 times a session and reaches ~48,000-52,000 events. It established that the harness declines to promote a mechanism-free signal **at that sample size**. F05's cells hold 6,965-17,051.

**No control can be built at F05's regime on this data.** Measured candidates at the once-a-session regime resolved in 2 of 12 combinations (`reports/control_candidates.md`), and F05 fires a few times a session, between that regime and F14's. So this null carries the §7.2 synthetic GARCH assurance - the harness does not promote idealised noise - and **nothing from F14**. Stated here rather than left for a reader to infer.

## Data

| instrument | trading days | 18:00-16:55 ET minutes traded |
|---|---|---|
| MGC | 4,005 | 64.16% |
| MNQ | 4,124 | 83.16% |

Armings whose full hold would not fit before 16:55 ET are excluded rather than truncated - a shortened hold is a different holding period, and §2's 17:00 hard exit requires the same of a real position. Excluded at most 2,155 on MGC, 1,795 on MNQ.

The row is the CME trading day, so the 17:00-18:00 maintenance break falls outside it rather than inside. MGC's 64.16% is thin overnight tape, not a data fault.

## Every cell

| instrument | vol_pct | k | hold | events | mean bps | Sharpe | p | |
|---|---|---|---|---|---|---|---|---|
| MGC | p15 | 1.5 | 60m | 12,327 | -0.28 | -0.0138 | 0.1716 |  |
| MGC | p15 | 1.5 | 120m | 11,825 | -0.08 | -0.0026 | 0.8110 |  |
| MGC | p15 | 1.5 | 180m | 11,361 | +0.06 | +0.0017 | 0.8492 |  |
| MGC | p15 | 2.0 | 60m | 10,189 | -0.42 | -0.0198 | 0.0624 |  |
| MGC | p15 | 2.0 | 120m | 9,800 | -0.25 | -0.0083 | 0.4502 |  |
| MGC | p15 | 2.0 | 180m | 9,468 | -0.23 | -0.0064 | 0.5763 |  |
| MGC | p15 | 2.5 | 60m | 8,139 | -0.33 | -0.0152 | 0.1844 |  |
| MGC | p15 | 2.5 | 120m | 7,839 | +0.06 | +0.0020 | 0.8440 |  |
| MGC | p15 | 2.5 | 180m | 7,590 | +0.13 | +0.0035 | 0.7509 |  |
| MGC | p20 | 1.5 | 60m | 15,454 | -0.31 | -0.0154 | 0.0873 |  |
| MGC | p20 | 1.5 | 120m | 14,795 | -0.17 | -0.0059 | 0.5204 |  |
| MGC | p20 | 1.5 | 180m | 14,183 | -0.16 | -0.0044 | 0.6445 |  |
| MGC | p20 | 2.0 | 60m | 12,844 | -0.39 | -0.0182 | 0.0555 |  |
| MGC | p20 | 2.0 | 120m | 12,328 | -0.36 | -0.0119 | 0.2206 |  |
| MGC | p20 | 2.0 | 180m | 11,881 | -0.50 | -0.0139 | 0.1654 |  |
| MGC | p20 | 2.5 | 60m | 10,286 | -0.26 | -0.0118 | 0.2452 |  |
| MGC | p20 | 2.5 | 120m | 9,888 | -0.08 | -0.0026 | 0.8205 |  |
| MGC | p20 | 2.5 | 180m | 9,556 | -0.27 | -0.0074 | 0.5076 |  |
| MGC | p25 | 1.5 | 60m | 18,591 | -0.31 | -0.0152 | 0.0643 |  |
| MGC | p25 | 1.5 | 120m | 17,783 | -0.17 | -0.0057 | 0.4973 |  |
| MGC | p25 | 1.5 | 180m | 17,029 | -0.14 | -0.0039 | 0.6522 |  |
| MGC | p25 | 2.0 | 60m | 15,520 | -0.38 | -0.0181 | 0.0365 | SEPARATES |
| MGC | p25 | 2.0 | 120m | 14,890 | -0.31 | -0.0103 | 0.2473 |  |
| MGC | p25 | 2.0 | 180m | 14,335 | -0.31 | -0.0085 | 0.3554 |  |
| MGC | p25 | 2.5 | 60m | 12,485 | -0.28 | -0.0127 | 0.1710 |  |
| MGC | p25 | 2.5 | 120m | 11,995 | -0.19 | -0.0062 | 0.5217 |  |
| MGC | p25 | 2.5 | 180m | 11,589 | -0.17 | -0.0047 | 0.6508 |  |
| MNQ | p15 | 1.5 | 60m | 10,325 | +0.06 | +0.0028 | 0.8583 | UNINFORMATIVE |
| MNQ | p15 | 1.5 | 120m | 9,907 | +0.08 | +0.0025 | 0.8939 |  |
| MNQ | p15 | 1.5 | 180m | 9,471 | +0.47 | +0.0120 | 0.3652 |  |
| MNQ | p15 | 2.0 | 60m | 8,235 | -0.20 | -0.0085 | 0.4695 | UNINFORMATIVE |
| MNQ | p15 | 2.0 | 120m | 7,898 | -0.16 | -0.0050 | 0.6535 |  |
| MNQ | p15 | 2.0 | 180m | 7,572 | +0.24 | +0.0060 | 0.6979 |  |
| MNQ | p15 | 2.5 | 60m | 6,292 | +0.17 | +0.0067 | 0.6432 | UNINFORMATIVE |
| MNQ | p15 | 2.5 | 120m | 6,060 | +0.41 | +0.0118 | 0.4265 |  |
| MNQ | p15 | 2.5 | 180m | 5,812 | +0.79 | +0.0188 | 0.2137 |  |
| MNQ | p20 | 1.5 | 60m | 13,089 | +0.02 | +0.0011 | 0.9651 | UNINFORMATIVE |
| MNQ | p20 | 1.5 | 120m | 12,538 | -0.16 | -0.0050 | 0.5835 |  |
| MNQ | p20 | 1.5 | 180m | 11,983 | +0.09 | +0.0023 | 0.9071 |  |
| MNQ | p20 | 2.0 | 60m | 10,544 | -0.25 | -0.0105 | 0.3228 | UNINFORMATIVE |
| MNQ | p20 | 2.0 | 120m | 10,101 | -0.38 | -0.0116 | 0.2866 |  |
| MNQ | p20 | 2.0 | 180m | 9,684 | -0.08 | -0.0019 | 0.8106 |  |
| MNQ | p20 | 2.5 | 60m | 8,134 | -0.04 | -0.0016 | 0.8729 | UNINFORMATIVE |
| MNQ | p20 | 2.5 | 120m | 7,819 | +0.02 | +0.0006 | 0.9933 |  |
| MNQ | p20 | 2.5 | 180m | 7,498 | +0.14 | +0.0034 | 0.8291 |  |
| MNQ | p25 | 1.5 | 60m | 15,824 | -0.04 | -0.0019 | 0.7935 | UNINFORMATIVE |
| MNQ | p25 | 1.5 | 120m | 15,163 | -0.17 | -0.0054 | 0.5165 |  |
| MNQ | p25 | 1.5 | 180m | 14,473 | -0.06 | -0.0014 | 0.7976 |  |
| MNQ | p25 | 2.0 | 60m | 12,818 | -0.30 | -0.0125 | 0.1968 | UNINFORMATIVE |
| MNQ | p25 | 2.0 | 120m | 12,278 | -0.39 | -0.0117 | 0.2274 |  |
| MNQ | p25 | 2.0 | 180m | 11,754 | -0.13 | -0.0032 | 0.6945 |  |
| MNQ | p25 | 2.5 | 60m | 9,978 | -0.09 | -0.0036 | 0.7137 | UNINFORMATIVE |
| MNQ | p25 | 2.5 | 120m | 9,589 | -0.07 | -0.0021 | 0.8160 |  |
| MNQ | p25 | 2.5 | 180m | 9,181 | +0.03 | +0.0006 | 0.9987 |  |

**54 trials.** 3 vol_pct x 3 k x 3 holds x 2 instruments.
