# T-series — the statistical character of price movement

**Status: S1 draft. Nothing registered. No trial spent.**

> **[§66] CLOSED 2026-10-02.** Nothing registered, no trial spent; the account of the close is
> `decisions.md` §66, and the discreteness finding is finding 11 of `programme_conclusion.md`.
>
> **[§65] Reviewed 2026-10-02. Still nothing registered, no trial spent; N = 760, SR\* = 0.1368.**
> The draft below is kept as written. Corrections are inserted as **[§65]** blocks, the P- and
> Q-series convention (§54, §59), so proposal and correction stay distinguishable. Every figure
> in a [§65] block is measured, and named with the report that measures it:
> `reports/t01_volume_clock.md`, `t05_sign_asymmetry.md`, `t02_t04_scale_collinearity.md`,
> `t_series_s2.md`. The account is `decisions.md` §65.

Every entry owes an S2 predicted magnitude checked against the BH bar at expected n,
an S2 scale-invariance check, an S3 measured firing rate, an S5 variance gate, and an
S6 control.

---

## The angle, and why it is orthogonal to all seven prior series

Across F, R, L, N, P, Q and S, every registered hypothesis conditioned on one of
exactly three things:

| axis | series |
|---|---|
| a price **level** | L (all), N02, N04/05 |
| a market **state** | P (all), S (all), F05, F09 |
| a **clock time** | F01–F04, F06, Q01–Q07 |

**Nothing has ever conditioned on the statistical character of the price path itself** —
how price arrived, rather than where it arrived or when. That is a fourth axis, it is
computable entirely from 1m OHLCV already on disk, and it is untested here.

> **[§65] Overstated.** Two registered entries already conditioned on the path's character:
> **F05** (volatility compression — the level of recent realised volatility, then the first
> k·σ breach) and **P03** (thin-move reversion — |return| per unit volume over the firing bar).
> T06 below is close to F05, and T02/T04's counterparty claim is P03's. The axis is less
> untouched than stated; the overlap is reported per entry.

Two things recommend it beyond novelty.

**It attacks a measured constraint rather than searching for a new effect.** The
programme's binding limits were sample size and cost, and three entries below act on
sample size directly by changing how observations are counted rather than by finding
more of them.

**It is where the measured pathologies live.** MNQ kurtosis of 115 and MGC of 226 were
treated throughout as nuisances to calibrate around. They are also information: a
distribution that fat is a mixture, and the mixture components may behave differently.
No series has conditioned on which component a given move belongs to.

### The honest prior

I expect most of this to fail, and the operative bar makes that near-certain: Sharpe
2.06 at 15% with ruin constrained, against a programme in which the single largest
positive effect ever measured (+0.452 bps gross) is negative net of cost.

**The realistic value of this series is T01**, which is not a hypothesis, and the
establishment of whether higher-moment conditioners carry any information at all —
a question with an interpretable answer either way.

---

# Class A — the measurement, not a hypothesis

---

## T01 — Volume-clock resampling

**Not a signal. Consumes no trials. May reopen previously blocked work.**

> **[§65] MEASURED** (`reports/t01_volume_clock.md`). It reopens nothing. Three corrections
> to the entry, then the result.

### What it is
Every bar in seven series has been a **calendar-time** bar: one observation per minute,
whether forty contracts traded or four thousand. A volume bar instead samples one
observation per N contracts traded — more bars when the market is active, fewer when it
is not.

### Why it matters here specifically
Calendar bars sampled during dead hours carry almost no information but count as full
observations in every n. That inflates nominal sample while contributing little
effective sample — which is the §45 unit error in a different guise, and the programme
has corrected that error three times at a cumulative cost of 2×, 12× and 62×.

> **[§65] There are no dead bars.** The continuous parquet has **zero** `volume == 0` rows in
> either product: an untraded minute is absent, not forward-filled. What a volume clock can act
> on is unequal weighting of *traded* minutes — MGC's volume per traded minute runs 1 to
> 10,400 contracts (p50 16, p99 723). The "2×, 12× and 62×" do not match the record: §45
> measured raw counts overstating effective n by **2.8–13.7×** and DEFF up to **65.6**.

Volume clocks are documented to produce returns closer to IID and markedly less
leptokurtic than calendar clocks. If MNQ's kurtosis of 115 falls materially under volume
sampling, three things improve at once: the bootstrap α calibration (fitted to kurtosis
that would no longer apply), the detection floor, and the DSR's γ₄ term.

> **[§65] Kurtosis does fall on MNQ; none of the three things follows.**
> - Measured at matched bar counts against a trade-minute clock: MNQ **86 vs 112, 39 vs 73,
>   20 vs 51** at three bar sizes. On MGC the one cell that passes the construction's own
>   pre-stated validity check goes the other way, **67 vs 30**; the two MGC cells that fail it
>   are withdrawn (see the trap below).
> - **Bootstrap α:** `calibration.md` §A already measured coverage at γ₄ = 115 and 226 and found
>   them indistinguishable. A 2× kurtosis gap does not move α\*, so a smaller one cannot.
> - **DSR γ₄:** n_min falls (e.g. 77 → 59 events) but it is tens of events against floors in
>   the thousands. It never bound anything.
> - **Detection floor:** a power floor on a *mean*, driven by σ and n. Not recalibrated under a
>   volume clock — argued, not measured, and labelled so.

### What it could reopen
Hypotheses blocked at S4 on effective n — **L01 (237 events), L08, F01 (4,125 against
19,722)** — were blocked on a count measured in calendar bars. If the effective count
rises under volume sampling, a blocked entry may become testable. That is not a
guarantee and may not move the number at all.

> **[§65] Nothing crosses, and two premises are corrected.** (1) **F01's 4,125 is the
> once-per-session data ceiling, not its firing count** — §22 measured the condition at
> **3,523 (MNQ) / 3,449 (MGC)** in its best cell and **66 / 115** in its worst. (2) These are
> counts of how often a *condition* fires. A clock changes them only by redefining the condition
> ("15 minutes away", "one 5m bar"), which is a new hypothesis. Gaps at each entry's best cell:
> L01 83× / 27×, L08 28× / 8×, F01 6× / 2× (MNQ / MGC). **No entry qualifies for
> re-registration; `hypotheses.yaml` is unchanged.**

### The trap, stated before measuring
**Resampling cannot create information.** If effective n rises, it must be because
calendar sampling was wasting observations, not because volume sampling manufactures
them. Verify by confirming the total information content is unchanged: same price path,
same realised variance, different partition. If effective n rises by more than the
reduction in dead-bar count explains, the calculation is wrong.

> **[§65] Effective n does not rise — it falls.** At a threshold equal to the mean traded-minute
> volume, MNQ's 2,540,069 traded minutes become 1,230,279 volume bars (**0.48×**), MGC's
> 3,547,109 become 1,467,042 (**0.41×**). The trap's premise is not reached.
>
> **The realised-variance half was applied as stated, and two cells fail it.** Before any
> result, the measurement said RV should be close across partitions at matched n, and that a
> large divergence would mean the construction is wrong. Raw ratios came back 0.69–0.96. One
> cause was tested rather than asserted — each series drops its session's first leg, which is
> longer on a volume clock — and restoring it gives **0.854–0.963**: a partial explanation that
> closes most of the gap on coarse bars and almost none on fine ones. **MGC at the two finer bar
> sizes stays outside ±10% and fails its own check; their kurtosis figures (164 vs 433, 65 vs
> 329) are withdrawn, not interpreted.** Whether the construction or the equal-variance premise
> is wrong there (MGC's tick is a fifth of its 1-minute σ; 14–15% of 1-minute returns are exactly
> zero) is not resolved.
>
> **A limit of the data, not of the idea:** built from 1-minute rows, a volume clock can merge
> quiet minutes but never split a busy one. At the mean-minute threshold 66% of MNQ "volume
> bars" are single minutes and 221,536 carry over 3× the threshold. A true volume clock needs
> tick or sub-minute data, which is not on disk.

### Deliverable
A measurement, logged to `measurements.jsonl`. Report, for MNQ and MGC: kurtosis at
calendar vs volume sampling across several bar sizes; effective n under each; and
whether any S4-blocked entry crosses its floor. **No reopening without a fresh
registration** — a hypothesis blocked under one sampling scheme and revived under
another is a new entry, not a continuation.

---

# Class B — decomposition of the move

---

## T02 — Jump versus diffusion

**Params: 3** | **Both instruments** | **Data on disk** | **Likely high firing rate**

### Mechanism
A price move of a given size can arrive two ways, and they are economically different.
A **jump** is information arriving faster than liquidity can absorb it. A **diffusive**
move of equal magnitude is the accumulation of ordinary two-sided trading.

Bipower variation (Barndorff-Nielsen & Shephard) separates them: realised variance
captures both, bipower variation is robust to jumps, and the difference isolates the
jump component.

The claim: **information has no reason to revert and liquidity consumption does.** A
jump re-prices the asset; a diffusive run of the same size partly reflects someone
working an order, and that pressure ends when they finish. Who pays: a participant with
an execution mandate. Why they persist: the mandate is not optional.

> **[§65] This counterparty claim has been tested.** P03 (thin-move reversion) is the same
> claim — liquidity consumption reverts — and measured only **0.86%** of a 9.18 bps excess
> displacement reverting at its own clock; real minus control **+0.079 bps** (§58).

### Condition
```
over a trailing window W:
    RV  = Σ r²                      (realised variance)
    BV  = (π/2) Σ |r_i||r_{i-1}|    (bipower variation, jump-robust)
    J   = max(RV − BV, 0) / RV      (jump fraction, scale-free)

if J < j_low  (move was predominantly diffusive):
    fade the W-window return
if J > j_high (move was predominantly a jump):
    no trade — registered as the falsification arm, not a second signal
exit at H minutes or 15:55 ET
```

> **[§65] The condition barely selects anything.** Measured over every 1-minute window
> (`t02_t04_scale_collinearity.md`), J < j_low holds in **60% / 83% / 94%** of windows on the
> index at j_low = 0.1 / 0.2 / 0.3 (MGC 57% / 82% / 94%). "Diffusive" describes almost every
> window, so the trade is nearly "fade every W-minute move". The falsification arm is the
> minority, not the control it is described as.

### Parameters
`W` ∈ {30, 60, 120} min · `j_low` ∈ {0.1, 0.2, 0.3} · `H` ∈ {30, 60, 120} min

J is a **ratio of variances and is scale-free**, so it satisfies §52 natively — but
verify rather than assert, since P03's ratio was called scale-invariant and was not,
because its denominator trended.

> **[§65] VERIFIED, AND IT IS NOT.** J is invariant to *multiplicative* scale — numerator and
> denominator come from one return series — but not to price **discreteness**. On a fixed tick
> grid a rising price shrinks the tick in bps, so fewer 1-minute returns are exactly zero.
> Bipower variation sums products of adjacent |r|, so each zero removes two of its terms and
> only one of RV's, inflating J. Measured at W = 60, 2010–2018 → 2019–2023 → 2024–2026:
>
> | | tick (bps) | zero 1m returns | J median | P(J < 0.2) |
> |---|---|---|---|---|
> | index (NQ→MNQ) | 0.56 → 0.20 → 0.12 | 18.3% → 5.6% → 3.1% | 0.093 → 0.050 → 0.049 | 0.77 → 0.87 → 0.88 |
> | MGC | 0.78 → 0.55 → 0.30 | 14.0% → 15.0% → 7.2% | 0.112 → 0.081 → 0.046 | 0.75 → 0.81 → 0.89 |
>
> J's median roughly halves on both, so a fixed j_low selects a different share of windows in
> each era. The direction of the mechanism is pinned by a synthetic test
> (`tests/test_t_series.py`); on MGC's middle era J falls while the zero share does not, so
> discreteness is not the whole account there. **Same failure class as P03, different channel:
> not a trending denominator, a price grid.** A registration would need j_low as a trailing
> percentile, as T03 already does.

### Predicted magnitude
2–5 bps if the mechanism holds, from the observation that execution-driven pressure is
the same class as the forced flow behind R01 (+0.452 measured). That estimate is weak
and it is a guess against a 3.71 bps bar at H=30.

> **[§65] The range contradicts its own anchor.** R01's +0.452 supports a magnitude near 0.5,
> not 2–5. The measured analogues of this counterparty claim — P03 +0.079, L12 +0.306, R01
> +0.452 — give **0–0.5 bps**. The 3.71 bar is the S-series' SR\* at N = 1,030, which never
> happened; at the N T02 would face (814), SR\* is **2.95–3.64 bps** at H = 30 (outright vs
> paired σ). Against that and its own BH bar (0.85–1.58): **below both** (`t_series_s2.md`).

### Why it might fail
- The jump/diffusion split is a statistical decomposition, not an observation of who
  traded. A thin-liquidity drift registers as diffusive and reverts for a reason the
  hypothesis does not claim.
- **J is strongly correlated with realised volatility**, so this may be a volatility
  conditioner wearing a decomposition label. The S6 control must match on volatility
  quantile, which `state_control.py` already does.
- Bipower variation is biased by microstructure noise at 1m sampling. Report the
  staggered-bipower correction alongside.

### Why it leads the class
It is the only entry here whose conditioning variable names a *distinction between two
kinds of counterparty* rather than a property of the price series. Everything else in
Class B conditions on a shape.

---

## T03 — Realised skewness

**Params: 3** | **Both** | **Data on disk**

### Mechanism
Amaya, Christoffersen, Jacobs & Vasquez document that realised skewness computed from
intraday returns predicts the cross-section of subsequent weekly equity returns —
negatively, with the lottery-preference interpretation that investors overpay for
positively skewed payoffs.

The time-series question at intraday horizon is untested here, and the mechanism is
different: a session with strongly negative realised skew experienced a few large down
moves among many small up moves, which is the signature of forced selling rather than
information. Who pays: a liquidation. Why they persist: margin and mandate.

### Condition
```
RSkew = (√n Σ r³) / RV^(3/2)   over a trailing window W   — scale-free
if RSkew < s_low:  long   (down-tail activity, fade the liquidation)
if RSkew > s_high: short
exit at H or 15:55 ET
```

### Parameters
`W` ∈ {60, 120, 240} min · threshold ∈ {p10/p90, p20/p80, p30/p70} · `H` ∈ {30, 60, 120} min

Thresholds are **percentiles, not values** — the §52 fix applied at registration rather
than discovered at S8.

> **[§65] Checked at W = 60 only** (the window T03 shares with T02/T04; 120 and 240 not run).
> Median RSkew stays near zero in every era and its p10/p90 hold at roughly ±0.84 to ±1.08 on
> both instruments, narrowing modestly on MGC. With percentile thresholds that drift does not
> reach the condition. **Acceptable at W = 60; not checked at the other two windows.**

### Predicted magnitude
1–3 bps. The equity cross-sectional result is weekly and cross-sectional; neither
property transfers, so this estimate is weaker than T02's.

> **[§65]** With no measured analogue in seven series and, by the draft's own account, nothing
> transferable from the cited result, the S2 prior is **0–1 bps**. That **clears T03's own BH bar
> (0.85 bps at H = 30, generous n) and sits below the prevailing SR\* (2.96 bps)** — the S-series
> finding again (terminal report §5, finding 9): an entry can pass its own correction and still
> establish nothing. The draft's 1–3 would straddle SR\* only at its very top.

### Why it might fail
Third moments are noisy. Realised skew at 60 minutes on 1m returns is estimated from 60
observations, and the standard error of a third moment at that n is large. The signal
may be mostly estimation error — which the S5 variance gate should catch.

---

## T04 — Path efficiency

**Params: 3** | **Both** | **Data on disk**

### Mechanism
Two paths with identical net displacement differ in how they got there. A straight-line
move is one-sided flow meeting no resistance; a zigzag of equal net size is contested,
with both sides active.

Efficiency ratio = |net displacement| / Σ|bar returns|, bounded in (0,1], and scale-free.

> **[§65] Verified scale-free:** median ER 0.106 / 0.112 / 0.111 on the index and
> 0.102 / 0.103 / 0.105 on MGC across the three eras.

The claim: **high efficiency means one participant and no absorption**, so when that
participant finishes, there is nothing holding the price. Low efficiency means two-sided
interest, so the level is supported. Same counterparty story as T02, measured
differently — which is why the two must be checked for collinearity before both are
registered.

### Condition
```
ER = |close_t − close_{t−W}| / Σ|r_i|
if ER > e_high and |net move| > k × ATR:
    fade the move
exit at H or 15:55 ET
```

> **[§65] The condition almost never fires.** Median ER at W = 60 is ~0.11: one-minute paths
> are overwhelmingly zigzag. ER > 0.5 holds in **0.19%** of index windows and **0.08%** of
> MGC's; ER > 0.65 in ~0.01%; **ER > 0.8 in none.** One third of the grid is empty by
> construction, and the rest fires a fraction of a window per session before the
> `|net| > k × ATR` clause (whose k and ATR the draft does not fix) removes more. Under the S2
> method T04 carries **~1–2 effective post-2021 units**, a BH bar of 59–218 bps.

### Parameters
`W` ∈ {30, 60, 120} min · `e_high` ∈ {0.5, 0.65, 0.8} · `H` ∈ {30, 60, 120} min

### Why it might fail
Efficiency and the jump fraction are likely to be substantially correlated — a jump
produces a high-efficiency path almost by construction. **Measure ρ(ER, J) before
registering both.** If it exceeds ~0.6 they are one hypothesis and only one should be
registered, per the Q01/Q02 finding.

> **[§65] MEASURED: they are not one hypothesis.** Spearman ρ(J, ER) on non-overlapping
> windows is **+0.047 to +0.073** across W ∈ {30, 60, 120} on both instruments — the predicted
> direction (a jump does make a path more efficient), a tenth of the 0.6 threshold. The test that
> mattered for Q01/Q02 was firing overlap, not conditioner correlation, and it agrees: at W = 60
> the two firing sets coincide *less* often than independence would give (index, j_low 0.2 /
> e_high 0.5: P(both) 0.0011 against 0.0015), Jaccard ≤ 0.0015. **Neither collinearity nor
> overlap blocks registering both. Each fails on its own:** T02 selects almost every window,
> T04 almost none.

---

# Class C — asymmetry

---

## T05 — Sign asymmetry

**Params: 3** | **Both** | **Data on disk** | **The cheapest entry here**

### Mechanism
**Every hypothesis in seven series was constructed sign-symmetrically** — the same rule
applied long and short, with direction set by the condition. That is a design choice
nobody examined, and it assumes up and down moves are mirror images.

They are not. Margin calls are triggered by losses, not gains. Forced liquidation is
one-directional. The leverage effect — volatility rising more after down moves than up
moves of equal size — is among the most robust asymmetries in empirical finance.

If the mechanism behind any reversion effect is forced flow, and forced flow is
predominantly triggered on the downside, then **a sign-symmetric test averages a real
effect with a null one and halves the measured magnitude.**

### What it actually is
Not a new signal. A re-examination of whether the programme's sign-symmetric
construction has been suppressing effects. It can be run against **already-measured
hypotheses at no new trial cost**, since the firings are on file — the same move that
made R06 free.

### Condition
```
for each previously measured entry with firings on file:
    split the measured effect by the sign of the conditioning move
    report long-side and short-side magnitude separately
    test whether the difference is itself significant
```

### Why this might matter more than any signal here
L07 returned 108 of 108 cells negative, pooled across both directions. If the effect is
−3 bps on one side and 0 on the other, that is a different finding from −1.5 bps on
both, and the registered conclusion does not distinguish them. The same applies to R01
and P03.

**If the asymmetry is real and large, several closed entries were closed on a pooled
statistic that averaged away their own mechanism.** If it is absent, the programme's
sign-symmetric design is validated and that is worth knowing too.

> **[§65] MEASURED** (`reports/t05_sign_asymmetry.md`). Every split is of numbers first
> **reproduced exactly** from the registered record — all 108 L07 cells from `l07_cells.json`,
> P03 from `p03_stage1.json`, all nine R01 cells from `r01_checks.json` — and every gap is
> tested with **sessions as the unit** (R01: non-overlapping entries, the independence its
> registered t already assumed). **No closed entry was averaging a real effect with a null.**
>
> | entry | up / long side | down / short side | gap | survives the split? |
> |---|---|---|---|---|
> | **L07 MNQ** | −1.11 to −4.73, negative 54/54 | −1.25 to −5.31, negative 54/54 | median +0.23; BH 0/54 | **yes** — weaker side ≥ 2.31× cost in every cell |
> | **L07 MGC** | −1.14 to −4.59, negative 54/54 | −1.18 to −5.44, negative 54/54 | median +0.13; BH 5/54 | **yes** — weaker side ≥ 1.76× cost in every cell |
> | **P03** | +0.133 (faded up-moves) | +0.025 (faded down-moves) | +0.11, p = 0.81 | **yes** — neither clears +0.625; real leg net of cost −0.32 / −0.24 |
> | **R01** (best cell) | +0.492 long | +0.411 short | +0.08, p = 0.41 | **yes** — both sides carry it; gap p 0.41–0.95, sign flips across cells |
>
> **L07 has one consistent, small lean.** On both instruments the down-created gaps (traded long)
> are the more negative side (52/54 and 48/54 cells), at 5–9% of the effect; it survives BH only
> on MGC, in one overlapping family. It also **closes an item open since the L-series**:
> `level_conclusion.md` asked whether a bullish/bearish mix difference could manufacture L07's
> sign through drift. A sign that holds separately on each side cannot come from the mix.
>
> **R01's long side alone (+0.492) nominally clears the 0.48 single-leg floor by 0.012 bps.**
> Selecting it would be choosing a subset by its result — the split is not significant
> (p = 0.41) and R01 needs two legs, against a 0.96 bps two-leg floor.

### Why it might fail
Splitting by sign halves n on each side, which raises both bars. An entry at the margin
pooled will clear neither split. Report the power loss explicitly.

> **[§65] Power, reported, and the nulls are reportable under §60.** Per-side SE is 1.42–1.45×
> pooled on L07 and ~1.5–1.6× on P03. Because "no asymmetry" is a null, the pipeline was required
> to recover an injected asymmetry **of the size sought — one side carrying the whole effect, the
> other none, a gap of 2 × |pooled| — at each run's own noise and n**. Recovered exactly and
> detected in every case: L07's least-powered cell on both instruments (power 1.00), all nine R01
> cells (power ≥ 0.995 in eight, **0.68** in W=120 k=2.5), and **P03 at power 0.82**, the
> weakest. P03 would likely miss a one-sided effect much under ~1.25 bps.

---

## T06 — Duration since last large move

**Params: 3** | **Both** | **Data on disk**

### Mechanism
Everything tested conditions on something happening. Nothing conditions on the **time
since it last happened**. Hazard-rate framing: if large moves cluster — and volatility
clustering says they do — then elapsed quiet is informative about the next arrival.

Distinct from L-series volatility compression, which conditioned on the *level* of
recent volatility. This conditions on **elapsed time since a threshold event**, which is
a different statistic and need not be monotone in volatility.

> **[§65] Volatility compression was F05, not an L-series entry** — and F05 is the closest
> registered hypothesis in the catalogue: "arm the setup, then trade the first close beyond k·σ"
> against T06's "arm after quiet, trade the first breach beyond k·σ in its direction". F05 is the
> one F-series hypothesis tested at adequate power (45 cells, 11,000–18,600 events) and it
> retired on a null (with §60's caveat on what that null can claim). Elapsed time and recent
> volatility level are different statistics; the trade they arm is the same.

### Condition
```
τ = minutes since the last |return| > k × trailing σ
if τ > p80 of its own trailing distribution:
    arm; trade the first subsequent threshold breach in its direction
exit at H or 15:55 ET
```

### Parameters
`k` ∈ {2, 3, 4} σ · `τ` percentile ∈ {70, 80, 90} · `H` ∈ {30, 60, 120} min

### Why it might fail
Forecasts magnitude, not direction — the same weakness that made the L-series
compression entry a coin flip on direction. Needs payoff asymmetry to survive, and the
win rate must come back near 50%. A hit rate meaningfully above that contradicts the
mechanism and indicates a bug.

> **[§65] Cannot state a signed magnitude**, by its own account (direction is a coin flip), so
> it cannot pass S2's magnitude check as written. Firing rate not measured.

---

# Class D — regime conditioning

---

## T07 — Variance-ratio predictability regime

**Params: 3** | **Both** | **Conditioner, not a signal**

### Mechanism
Not a claim that the market is predictable. A claim that **the market's own degree of
serial dependence is measurable and time-varying**, and that a mean-reverting strategy
should be inactive when the variance ratio says the series is trending.

VR(q) = Var(q-period return) / (q × Var(1-period return)). Above 1 is persistence,
below 1 is reversion, 1 is a random walk. Scale-free.

### Use
Register as a **conditioner applied to a surviving primary**, exactly as Q08 was.
There is currently no surviving primary, so this is contingent — state that rather than
ranking it as a standalone.

### Why it might fail
VR is estimated with wide error at intraday windows, and the estimate is itself
autocorrelated. It may condition on nothing more than recent volatility.

> **[§65]** No primary survives, so there is nothing to condition and no magnitude to state.

---

# Registration order, and the honest ranking

| # | id | rationale |
|---|---|---|
| 1 | **T01** | no trials, no new data, attacks the binding constraint, may reopen blocked work |
| 2 | **T05** | no new trials — reanalysis of firings on file, and could change the reading of closed entries |
| 3 | T02 | the only entry whose conditioner names a counterparty distinction |
| 4 | T04 | **only after ρ(ER, J) is measured** — may be T02 restated |
| 5 | T03 | real literature, but weak transfer and a noisy estimator |
| 6 | T06 | magnitude-only; direction is a coin flip |
| — | T07 | contingent on a surviving primary, which does not exist |

**T01 and T05 cost no trials and should be run before anything is registered.** Both are
measurements. Between them they either change the detection floor or change the
interpretation of four closed entries, and neither raises SR\* for future work.

> **[§65] Both ran first, as recommended; neither changes anything.** T01 improves a floor that
> never bound (on MNQ; on MGC its two strongest cells fail their own check), and T05 finds every
> closed entry's conclusion intact on both sides. Then the S2 filter, with no trial spent:
>
> | | prior | own BH bar | SR\* (bps, at its N) | binds | disposition |
> |---|---|---|---|---|---|
> | T02 | 0–0.5 | 0.85 | 2.95 | SR\* | below both; condition near-unconditional; J not scale-free |
> | T03 | 0–1.0 | 0.85 | 2.96 | SR\* | **clears its own bar, below SR\*** |
> | T04 | 0–0.5 | 59–218 | 2.98 | BH bar | below both; almost never fires |
> | T06 | cannot predict | | | | F05 restated |
> | T07 | cannot predict | | | | no primary |
>
> **Nothing is recommended for registration.**

---

## What would make this series worth having run

Not a promotion. The realistic outcomes, in descending order of value:

1. **T01 shows effective n rises materially under volume sampling**, which would mean
   seven series measured their binding constraint on a sampling scheme that wasted
   observations. That is a method finding affecting everything already closed.
2. **T05 shows sign asymmetry is large**, which would mean several entries were closed on
   a pooled statistic that averaged a real effect with a null one.
3. **Both come back flat**, which validates the programme's sampling and sign-symmetric
   design and costs nothing.

If T02 through T06 all come back null at adequate power, the statistical-character axis
is closed alongside level, state and time — and the fourth and last structural dimension
reachable from data on disk has been searched.

**State plainly in that case that it is the last axis, not that it is time for a ninth
series.** Three axes were closed by seven series; this closes the fourth. What remains
after it requires data purchases or an account structure that permits constructions this
one does not.

> **[§65] Outcome 3 occurred, with one qualification.** T01 did not raise effective n (it
> lowers it), and T05 found no closed entry averaging a real effect with a null — the
> sign-symmetric design is validated on L07, P03 and R01, at power the §60 standard accepts.
>
> **The qualification is on the last paragraph.** T02–T06 did not "come back null at adequate
> power": none was run. They were closed at S1–S2 by arithmetic and by measured properties of
> their own conditions. That is a stronger reason not to run them, and a weaker claim about the
> axis. **The statistical-character axis is not shown empty by evidence; it is shown not worth
> searching with these instruments, on this data, at this cost** — and the data limit is
> specific: a true volume clock, and any jump/diffusion split free of the 1-minute tick grid,
> both need trade-level data that is not on disk. Per §61, that is a reason to stop, not a ninth
> series.
