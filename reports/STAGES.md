# S1–S8 — the canonical stage numbering

**One numbering across the whole programme.** Every document, every run report, every
`decisions.md` entry and every session refers to the same thing by the same number.

Adopted 2026-09-12. It replaces the ad-hoc "Stage 0 / Stage 1" language, which named only two
of the eight things actually being done and left the rest unnumbered — which is how L11's
placebo came to be measured before anything checked that its condition discriminated.

---

## The stages

| | stage | the question it answers | what failing it means |
|---|---|---|---|
| **S1** | **Mechanism** | Who is losing money to you, and why do they keep doing it? | There is no trade, only a pattern |
| **S2** | **Pre-registration** | Is every parameter fixed before testing? | Any result is a selection, not a finding |
| **S3** | **Firing rate** | How often does it actually fire, measured on real data? | The event count is unknown, so nothing downstream is interpretable |
| **S4** | **Detection floor** | Is effective n above the smallest detectable edge? | The test cannot produce evidence either way |
| **S5** | **Condition validity** | Does the condition discriminate at all? | The treatment is not a treatment |
| **S6** | **Placebo** | Real level vs distance-matched arbitrary level | A raw statistic measures exposure, not reaction |
| **S7** | **Multiplicity** | Trial log, N, SR\*, BH correction | A result is indistinguishable from having looked many times |
| **S8** | **Out-of-sample and economics** | Era split, other instruments, cost floor | An effect that is real and unprofitable, or real and gone |

### S3 — measured, never declared
`decisions.md` §21: F02 declared one firing per session and produced 106–707 events per cell
against a predicted 4,006–4,125. **Wrong by a factor of forty.** A declaration has no
independent source, so no test can check it. The gate reads `reports/measured_rates.json` and
nothing else.

### S4 — effective n, not raw firings
A position held H minutes cannot restart until it closes, so overlapping entries are **one
observation counted many times**. The number that matters is non-overlapping events, further
reduced for serial dependence. Raw counts overstate by 2.8×–13.7×.

### S5 — condition validity, and it is a GATE
**No condition proceeds to S6 until it passes S5.** The check has three parts:

1. **Firing-minute variance.** Entry-minute min/max/sd per cell. A condition that fires at a
   fixed minute is not selecting events.
2. **Parameter discrimination.** Adjacent parameter settings must change *which* events fire,
   not merely *when*. If two settings share 0% of entry minutes but 100% of the events, the
   parameter is an offset.
3. **Directional collapse.** Where a level set carries a high and a low, they must not fire at
   the same `(row, minute)` — if they do, the two sides are one event with opposite labels.

Degenerate signature, measured: every level fires, sd ≈ 0, adjacent settings share no minutes,
high/low collision 92–99%. Sound signature: counts fall with the threshold, sd 16–370,
collision 1–4%.

### S2 — a registered prediction must be checked for reachability
**Added 2026-09-12 after L12 (§45).** A registration that states a predicted magnitude must
also record the effect size a BH survivor would require at the expected n. L12's prediction of
+1.3 to +3.5 bps carried a mandatory significance limb whose threshold was **2.82 bps** — so
it was reachable only in the top fifth of the range, and 6.8% likely at the bottom of it.
Nobody noticed until after the run.

**The check SURFACES the problem; it does not auto-reject.** A prediction below the reachable
threshold is often still worth testing, and rejecting by default would filter out exactly the
small-effect hypotheses that matter on cost grounds. Three legitimate responses: register it as
an **economics-only test with the significance limb explicitly waived** (what L12 should have
been), **increase n**, or **proceed knowingly** with the low power recorded so a null cannot
later be read as evidence of absence.

**The audit that followed found something larger:** of 26 registrations across the F-, R- and
L-series, **L12 is the only one that ever stated a magnitude at all.** So the check should
require a magnitude or an explicit waiver, not merely validate one when volunteered.

### S2 — thresholds must be scale-invariant over the sample
**Added 2026-09-13 after N02 (§51, §52).** A registered threshold must be scale-invariant over
the sample it runs on (bps, volatility units or ATR multiples), **or** the registration must
state the price range the sample spans and pre-register an era split.

The reason: the spliced NQ/MNQ index rose **14×** from 2010 to 2026. A threshold fixed in ticks
or points therefore ran a **different trade in each era**, all pooled into one cell. N02's
8-point break was a 41 bps move in 2010 and a 2.9 bps move in 2026.

**No existing gate can see this.** S5 checks that a condition selects events and S6 checks that
the placebo is matched. Both are computed on the pooled sample, so both pass while the
condition drifts by an order of magnitude underneath them. Scale stationarity is a property
across **time**, and nothing looked there.

**Surface, don't reject**, as with the magnitude check. A point threshold can be a legitimate
choice (round-number *levels* are round because they are in price units), but the registration
must say so and carry the era split.

### S8 — run the era split by default, not on suspicion
N02's era split was requested because R01 had decayed after 2024. It found a mechanical
artifact instead: the sign flip was the 14× scale drift, not decay. **A check aimed at one
failure found a different one.** That is the case for running it on every S7 result as a
default, rather than only when a specific failure is suspected.

### S6 — the placebo is an arbitrary region at a matched distance
Redefined 2026-09-09 (§37). **It is a weaker control than a displaced real level**: it
equalises where a region sits and how often price reaches it, and **nothing about how price
arrived**. A result under it means "behaves differently from an equally-reachable arbitrary
region", which is weaker than "behaves differently given the same approach", and must be
written in those words.

**For a STATE condition the control is different in kind, and so is what can block it**
(§54, §55). A state has no location, so there is no region to displace; the matched control
draws each firing a partner from a different session in the same time-of-day bucket,
volatility quantile and year, where the state does not hold. Two modes, and **the choice is
forced by the firing rate rather than chosen**:

| state | fires | mode |
|---|---|---|
| frequent (P03-like) | many times per session | `bar` — strict is structurally unavailable |
| session-level (P01-like) | about once per session | `strict` — bar mode would draw the control from inside the state |

**A CLEAN-POOL CHECK IS A REGISTRATION-TIME REQUIREMENT for any session-level state**, not a
diagnostic run afterwards. Strict mode needs sessions in which the state never fires, and a
state with a trending or high base rate does not have them: on NQ a P03-shaped state touches
92.6% of sessions and the 265 survivors range from 0% of 2011 to 17.5% of 2025. A session-level
state whose clean pool is thin **has no valid control and is not registrable** — the same
disposition as L06, whose levels sit at the reference price and admit no matched region.
`session_clustering()` reports the numbers the entry must cite.

### S7 — the trial log is the denominator
Every comparison appends before it runs. N drives SR\*; BH corrects within a hypothesis.
Cells that overlap heavily are not independent tests, which makes BH conservative — and also
means a raw count of separations overstates the evidence. Both directions get recorded.

### S8 — economics decides, not the p-value
At large event counts separation is close to assured for any effect that is not exactly zero.
The deciding number is effect size against the measured cost floor, plus whether the effect
survives an era split and appears on another instrument.

---

## Mapping the old language

**Historical `decisions.md` entries are NOT rewritten.** They were true when written and
rewriting them would destroy the record of what was known when. Read them through this map:

| old | new | note |
|---|---|---|
| "Stage 0" / registration | **S1–S2** | mechanism + pre-registration |
| "Stage 1" | **S6–S8** | placebo comparison, BH, economics |
| detectability / firing-rate work | **S3–S4** | was never called a stage |
| — | **S5** | **had no name at all until 2026-09-12** |

**S5 is the stage that did not exist, and its absence is the finding.** See below.

---

## Where each hypothesis stopped

| | stopped at | |
|---|---|---|
| L01, L05, L08, L09 | **S4** | below the detection floor |
| L06 | **S6** | no valid control exists — levels sit at the reference price, so there is no distance to match |
| L11 | **S5** | withdrawn; condition fired unconditionally |
| L02 sweep arm | **S5** | withdrawn; same defect |
| L02 absorption, L03 | **S7** | retired on a null |
| L04 | **S7** | inconclusive — nominal hits, no BH survivor |
| L07 | **S8** | retired; refuted on economics |
| L10 | — | the placebo control itself; spends no trials |
| L12 | pending | registered at S1–S2; S3–S4 measured; awaiting S5 |

---

## The ordering finding, 2026-09-12

**L11's S6 placebo was measured before anything verified its condition discriminated.**

The matching came back clean — distance ratios 0.90–1.06, touch ratios inside tolerance, all
four level types passing. Those numbers were **meaningless**, because the treatment had not
cleared S5: the condition fired unconditionally at a fixed minute on every session, so the
entry population was "every session at 10:31" and distance-from-price was fixed by
construction. A placebo matched against a degenerate treatment tells you nothing about either.

**The check that would have caught it was built reactively, after L11 had already failed.**
It then found the same defect in L02's sweep arm and L05 — two more registered hypotheses,
one of them Tier A and graded B. A check that exists only because something already went
wrong is not a gate; it is a post-mortem.

**S5 is therefore a permanent gate.** No condition proceeds to S6 until it passes. The cost of
running it is minutes; the cost of not running it was three hypotheses, one of which was
carried for a day with a clean-looking placebo report attached to a condition that could not
select events.

**Corollary: S6 results computed before S5 passed must be discarded, not reinterpreted.**
L11's 0.90–1.06 ratios are recorded in its registry entry under `degenerate_measurements` with
exactly that warning.
