# Handoff brief — P-series closed, Q-series designed

For a fresh session with no conversation history. Nothing in the Q-series is
registered. No trial has been spent on it.

> **REVIEWED 2026-09-13 — `reports/decisions.md` §59.** Kept as written, with corrections inserted
> where they apply, marked **[§59]**. Two sections are materially wrong:
> **"The account structure"**, whose drawdown rule was assumed rather than confirmed, and
> **"The twelve candidates"**, which does not know that Q01, Q03 and Q04 are already in the
> registry as F02 and F12. Read `Q_SERIES_FINAL.md` and §59 alongside this.

---

## Programme state

**Five series closed. N = 760, SR\* = 0.1368, nothing promoted, ever.**

| series | registered | outcome |
|---|---|---|
| F | 14 | closed on sample size |
| R | 5 | R01 real but uneconomic (+0.45 vs 0.96 bps floor); R02 no persistence; R04 blocked on account permission |
| L | 12 | closed — S4 blocks, S5 withdrawals, S6 uncontrollable, S7 retirements |
| N | 10 candidates | 1 tested (N02), retired at S7 |
| P | 13 candidates | 1 tested (P03), retired at S7 |

> **[§59] "F: closed on sample size" hides the entries the Q-series re-proposes.** F02 is the conditional
> overnight drift (run, 144 trials, `stage1_uninformative`), F12 the pre-FOMC drift (excluded), F13 the
> unconditional overnight drift (excluded).

Last commit: `bca2f03`. Repos under `coltontr419-droid`:
`futures-research`, `r-series-research`, and `online-income-research`
(consolidation of all projects as git subtrees).

**Machine:** laptop ~2.7 GB RAM, has OOM-killed processes repeatedly.
`f01_rates` cannot complete a full run there. Data is gitignored — code
syncs between machines, data does not.

---

## How the P-series died

Thirteen candidates in non-price observable classes. One registered, one
tested, zero promoted, 1 trial spent.

**P03 (thin-move reversion, Amihud-style)** was the only one to reach S7.
Retired on its pre-registered clause:

```
real leg gross       +0.2004 bps
real leg net of cost -0.2796 bps   <- loses money before significance matters
real - control       +0.0794 bps
pre-registered bar   +0.625 bps    -> 7.9x short
```

Measured reversion was 0.86% of the excess against 6.8% required. The
economics limb refuted on its own — the real leg is negative net of cost, so
no power argument was needed. Era split showed no sign flip and no
era-specific effect; because P03's threshold is a rank rather than points,
the split is interpretable, unlike N02's.

Gates all passed before the run: S5 (entry-minute sd 110.2 over 380
minutes), S6 MATCHED in bar mode (27,437/27,437 paired, 0.0% era fallback).

### What the P-series produced that outlives it

1. **A matched control for state conditions** (`state_control.py`, 17 tests).
   The level placebo transposed: match the nuisance (time-of-day bucket,
   volatility quantile, year), vary the claim (state holds vs doesn't).
   Fault-injected three ways — a regime-loaded fake with no information beats
   a rotation null (danger confirmed real), does *not* beat the matched
   control, and a genuine state effect does.

2. **The mode partition**, now an S6 registration-time requirement.
   Frequent states require bar mode because strict is structurally
   unavailable; session-level states require strict mode, which fails when
   clean sessions are scarce. A session-level state with a thin clean pool
   has no valid control and is not registrable — same disposition as L06.

3. **Outcome fault-injection for nulls.** `tests/test_p03_outcomes.py` pins
   four properties: an injected +4.0 bps reversion is recovered as +3.45, a
   pure random walk returns zero, the hold never crosses a session boundary,
   and an extending move costs the fade rule money. **A null is only
   reportable from a pipeline demonstrated to recover an injected effect of
   the size being sought.** Five series of mostly-null results had never
   established this. Should be standing in §46.

   > **[§59] Proposed, not adopted.** Recorded in §59 as a proposal left for decision.

4. **The √2 reversal.** A proposed correction to inflate the SE for a
   difference-of-two-means statistic was itself wrong — the §45 anchor was
   *already* a difference SE (64.7/√4052 = 1.016). Repo swept: three bar
   computations, all difference statistics, no other occurrence. Recorded
   because the error appeared *inside a correction*, where provenance is
   least likely to be checked.

5. **Economics-binding regime.** At H=15 the cost floor (0.48) sits at the
   BH bar (0.463–0.625). Below roughly that horizon cost dominates and
   significance stops being the constraint. First time in five series the
   programme hit the boundary from that side.

---

## The Q-series — design, not yet registered

### The target, decomposed

Stated goal: 1–5%/month, with 4% losses rare.

For Sharpe S at annual vol σ, P(ever hitting drawdown D) ≈ exp(−2SD/σ).
Requiring that near 5% at D = 4%:

| monthly | annual | Sharpe required |
|---|---|---|
| 1% | 12% | **2.12** |
| 3% | 36% | 3.67 |
| 5% | 60% | 4.74 |

**The upper half of the range is not reachable.** Sharpe 2.12 needs a
**4.50 bps net edge** at ~2,000 trades/year — against a five-series maximum
observed effect of 5.0 bps (L07, wrong sign, mechanism refuted).

> **[§59]** 64.7 bps, behind the 4.50 figure, is the §45 SE-scaling anchor for a real-minus-placebo
> difference at 180 minutes, not a per-trade SD. The target arithmetic is order-of-magnitude only.

### The structural consequence: it must be a portfolio

| each Sharpe | k=3 | k=4 | k=6 |
|---|---|---|---|
| 1.0, ρ=0 | 1.73 | 2.00 | 2.45 |
| 1.0, ρ=0.1 | 1.58 | 1.75 | 2.00 |
| 1.0, ρ=0.3 | 1.37 | 1.45 | 1.55 |

One edge at Sharpe 2.1 has never been found in five series. Four to six at
Sharpe ~1.0 with ρ ≤ 0.1 reaches the same place. **This requires a design
change** — the series is built as a portfolio from the start, with
cross-correlation measured and registered rather than hypotheses tested in
isolation. Event and calendar edges are the natural material because they
fire on different days and are structurally low-ρ.

### The warning that should shape expectations

The best-documented large anomaly in this exact instrument class was
**publicly declared dead in July 2026 by the authors who found it.**

Boyarchenko, Larsen & Whelan (NY Fed Staff Report 917) documented the
"overnight drift" — almost the entire US equity premium earned between
2:00–3:00am ET when European markets open, ~3.6% annualized over 1998–2019,
significant on every weekday and in 9 of 12 months. Mechanism: dealer
inventory risk from end-of-day order imbalances, Grossman-Miller (1988),
with the testable prediction that drift is larger after sell-offs.

Liberty Street Economics, *The Disappearing Overnight Drift* (July 2026):
that window has averaged close to zero since 2021.

**Every Q-series candidate must report pre-2021 and post-2021 separately.
An era split is mandatory, not optional.**

> **[§59]** The registry recorded this on 2026-08-28: F13 excludes the unconditional drift on exactly
> this ground, and F02 is the conditional version, already run.

### The twelve candidates

Full document: `Q_SERIES_FINAL.md`.

| id | hypothesis | note |
|---|---|---|
| Q01 | conditional overnight drift, post-selloff | **strongest** — see below |
| Q02 | end-of-day imbalance reversal | same mechanism, opposite window, low-ρ vs Q01 |
| Q03 | pre-FOMC drift | ~48 events/6yr, economics-only |
| Q04 | macro release windows | better as exclusion (Q11) |
| Q05 | turn-of-month | cleanest "who pays and cannot stop" |
| Q06 | day-of-week overnight seasonality | high k, easiest to overfit |
| Q07 | roll-window flow | uses the 672 unparsed spread files |
| Q08 | volatility-managed sizing | **now primary — see account section** |
| Q09 | drawdown-aware scaling | **now primary** |
| Q10 | post-2021 split as standing S8 gate | not a hypothesis |
| Q11 | event-window exclusion | serves the drawdown constraint |
| Q12 | cross-edge correlation matrix | **load-bearing** — the portfolio route fails at ρ=0.3 |

> **[§59] Corrected notes, measured 2026-09-13:**
>
> | id | correction |
> |---|---|
> | Q01 | **is F02** (87.1% firing overlap); data on disk is not out of sample; S2 STRADDLES (0–3 vs 2.81–3.89 post-2021) |
> | Q02 | **conditioner Spearman +0.972 with Q01, same side on 100% of Q01 nights**; its hold as written crosses 17:00; S2 BELOW |
> | Q03 | **is F12, excluded** (event count, 17:00 exit); S2 BELOW (0–25 vs 30.6–42.5) |
> | Q04 | **covered by F12's note** ("do not register them individually"); no direction |
> | Q05 | S2 BELOW post-2021 (0–10 vs 16.4–22.7) |
> | Q06 | S2 BELOW even with Monday pre-registered (0–3 vs 10.6–14.7) |
> | Q07 | no direction; cannot be predicted |
> | Q08, Q09 | **not primary** — sizing cannot substitute for edge (36.8% at any size with no edge); Q09 computed at S1 |

**Why Q01 leads:** it is the only hypothesis in six series where a published
effect's death is *evidence for* the mechanism surviving. Arbitrage competes
away the unconditional free lunch first; compensation for actually bearing
inventory risk after a sell-off is harder to arbitrage. The conditional
version — long from ~01:45 to ~03:15 ET only after bottom-tercile
end-of-day imbalance days — may survive.

> **[§59]** That argument was made on 2026-08-28 in F13's exclusion note, and F02 was registered on it and
> run. The Q-series is not the first place it appears.

Recommended order: Q01, Q02, Q05, then Q08, then Q12 once three edges exist.
Q10 and Q11 are standing gates.

> **[§59] This line and the "now primary" labels above disagree with each other.** Resolved in §59: edges lead,
> Q09 is complete, Q08 waits for a survivor — and on the S2 filter no edge is registrable on disk data.

---

## The account structure is currently a harder constraint than the market

> **[§59] SUPERSEDED — THE RULE BELOW WAS ASSUMED, NOT CONFIRMED.** Confirmed with the firm: the floor starts 4%
> below the starting balance and trails the running equity peak. **It becomes static when it reaches the
> starting balance, which happens when the peak reaches +4%, not +10%,** and then sits at breakeven
> permanently. This section is kept as written so the superseded arithmetic stays visible; the corrected
> arithmetic is in `reports/q09_drawdown.json` and §59. Same class as R04, where a constraint was assumed
> to have a lever it did not have.

**Rule: 4% trailing drawdown until +10% is made, then static.**

This was established late and it inverts the sizing decision. The earlier
`exp(−2SD/σ)` figures were the *static* case. A trailing floor measures from
the running peak, so the right question is: does the account reach +10%
before ever giving back 4% from a high?

P(reach +10% before a 4% trailing drawdown):

| Sharpe | sized 1%/mo | sized 0.5%/mo | sized 0.25%/mo |
|---|---|---|---|
| 1.0 | **17%** | 30% | 61% |
| 1.5 | 34% | 46% | 83% |
| 2.1 | 64% | 76% | 95% |

> **[§59] Only partly reproducible, even under its own assumed rule.** The trailing-drawdown formula (Taylor
> 1975, Lehoczky 1977) reproduces five of these nine cells within 2.3 points, one within 5, and misses
> three by 13–22 points (1.5 at 0.5%/mo gives 67.5%, not 46%; 1.5 at 0.25% gives 96.3%, not 83%; 2.1 at
> 0.5% gives 96.0%, not 76%). No single finite horizon reproduces the set either: the best, five years,
> still misses one cell by 24 points. Its provenance is recorded as unverified.
>
> **[§59] Corrected — P(peak reaches +4% before a 4% trailing drawdown):**
>
> | Sharpe | 1%/mo | 0.5%/mo | 0.25%/mo |
> |---|---|---|---|
> | 1.0 | 49.5% | 62.0% | 81.9% |
> | 1.5 | 65.0% | 85.5% | 98.5% |
> | 2.1 | 84.9% | 98.4% | 100.0% |
> | **0.0** | **36.8%** | **36.8%** | **36.8%** |
>
> A driftless walk reaches the lock with probability exp(−1) = 36.8%, **not 50%**. The 50% figure belongs
> to a STATIC barrier; a trailing floor follows every new high up. Verified by trade-level Monte Carlo
> (the continuous formula is conservative by 1–3 points; Student-t tails move it by under 1 point).

**Phase 1 is the entire risk.** After the floor locks there is ~6% of
cushion and the problem largely disappears. Before that, every new equity
high drags the floor up behind you — making money is what creates the next
chance to bust.

> **[§59]** At the confirmed lock the cushion is **4%, not ~6%** — smaller at the moment of locking — but it
> is the accumulated profit, so it grows without bound.

**Sizing for 1%/month is how you never reach 1%/month.** At the realistic
Sharpe from a three-edge portfolio (~1.5), targeting 1%/month gives a 66%
chance of busting before the floor locks.

> **[§59]** Under the confirmed rule, Sharpe 1.5 targeting 1%/month busts before the lock **35%** of the time, not 66%.

### The sizing rule that follows

- **Phase 1 (0 → +10%):** size for ~0.25–0.5%/month. Survival is the
  objective, not return. ~3.3 years to +10% at 0.25%/month, Sharpe 1.5.
- **Phase 2 (locked floor):** size up roughly 3–4×, per the static-floor
  arithmetic.

> **[§59] Phase 1 is 0 → +4%.** Median time to lock at Sharpe 1.5: **0.45 years at 0.5%/mo, 1.14 at 0.25%/mo.**
>
> **[§59] The 3–4× step-up does not survive as a step.** With the floor static at breakeven and a 4% cushion
> at lock, a Sharpe 1.5 strategy at 0.5%/mo has a 5.0% lifetime breach probability at 1×, **36.8% at 3×
> and 47.2% at 4×**. What survives is sizing proportional to the cushion: holding the breach probability
> fixed, 3× is earned at +12% and 4× at +16%. The residual risk is a single trade larger than the cushion
> — at most 1.7 in 1,000 over five years under Student-t tails in these cells, though intratrade adverse
> excursion is not modelled.

This reorders the series: Q08 and Q09 are primary work, not support. At
Sharpe 1.5 the gap between 34% and 83% survival is entirely a sizing choice,
and no edge in the Q document moves the number that much.

> **[§59] The demotion does not hold.** Corrected, Sharpe 1.5 runs from 65.0% at 1%/mo to 98.5% at 0.25%/mo —
> 33.5 points, not 49 — and at the realistic middle sizing it is already 85.5%. More decisively, with no
> edge the probability is 36.8% at EVERY size: at 4% annual vol, moving from no edge to Sharpe 1.5 adds
> 48.7 points, while no sizing adds anything to a zero edge. Sizing multiplies an edge and cannot
> substitute for one, so edges lead and Q08 waits for a survivor.

**Open question to confirm before Q09's calculation:** where the floor locks
when it goes static — at +6%, or at the starting balance. Does not change
Phase 1; changes how aggressively Phase 2 can be sized.

> **[§59] Answered:** at the starting balance, and it changes Phase 1 too — the lock arrives at +4%.

---

## What would make the Q-series a success

Not a promotion. **Three edges at Sharpe ~1.0 with measured ρ ≤ 0.1**,
combining to ~1.6–1.7, supporting roughly 0.7%/month within the drawdown
constraint. That is short of the stated target and is the realistic best
case.

If Q01, Q02 and Q05 all come back null — which the base rate says is likely
— then six series have searched this space and the correct conclusion is
that no edge accessible at this cost structure and account size exists in
intraday and calendar futures signals. **That is a real finding and should
be written as one, not treated as a reason to start a seventh series.**

---

## Standing method (S1–S8)

Canonical reference: `reports/STAGES.md`.

- **S1** Mechanism — who is losing money to you, and why they keep doing it
- **S2** Pre-registration — parameters fixed a priori, predicted magnitude
  checked against the BH bar at expected n, scale-invariance check (§52)
- **S3** Firing rate measured, never declared
- **S4** Detection floor vs effective n
- **S5** Condition validity — negative control, fault injection,
  firing-minute variance gate
- **S6** Placebo/control — matched at `valid_from` (measures reachability);
  state conditions use `state_control.py`; clean-pool check for
  session-level states
- **S7** Multiplicity — hash-chained trial log, N, SR\*, BH
- **S8** Out-of-sample and economics — era split (now mandatory), other
  instruments, cost floor

### Transferable findings from six series

`confirmed_break` defect · missing-magnitude gap · S5-before-S6 ordering
error · placebo convention (`valid_from` = reachability, tested and held) ·
session-vs-event unit of observation (DEFF 1.14–65.6) · scale invariance
(14× index move) · mode partition · outcome fault-injection for nulls.

Each was found because something got measured that did not have to be.

### Working rules

Push at the end of every task touching tracked files; never force-push. Log
decisions in `decisions.md` rather than resolving silently. If a result
looks strong, look for the bug before celebrating. Fix registry defects in
the entry, never by loosening a test. Never write a number that was not
computed that turn.

> **[§59] Add one:** read `hypotheses.yaml` before drafting a series. Three of twelve Q candidates were
> already registered, and one had already spent 144 trials.

"Nothing found" is a complete result when the test had the power to find
something. Say it plainly and stop, rather than widening the search until
something appears.
