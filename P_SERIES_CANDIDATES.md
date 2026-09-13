# P-series candidates — non-price observables

Status: **S1 draft. Nothing registered, no magnitudes committed.** Every entry
needs the S2 magnitude check, the S2 scale-invariance check (§52), an S5
variance gate, and an S6 placebo before it means anything.

> **REVIEWED 2026-09-13 — `reports/decisions.md` §54.** Magnitudes predicted for all
> thirteen; control design settled; data claims verified against disk. Corrections are
> inserted in the entries they concern, marked **[§54]**. The draft text is otherwise
> preserved as written, so what was proposed and what was corrected stay distinguishable.

---

## Two constraints that shaped the list

### Horizon is not an escape

At constant signal quality (per-trade Sharpe 0.031, from L12-era effects):

| horizon | sd | trades/yr | effect | eff/cost | n (6yr) | bar | eff/bar |
|---|---|---|---|---|---|---|---|
| 180m | 65 | 2,000 | 2.0 | 4.2 | 12,000 | 1.6 | **1.22** |
| daily | 130 | 250 | 4.0 | 8.4 | 1,500 | 9.3 | 0.43 |
| weekly | 291 | 52 | 9.0 | 18.8 | 312 | 45.7 | 0.20 |
| monthly | 596 | 12 | 18.5 | 38.5 | 72 | 194.8 | 0.09 |

Same shape as §45's selectivity finding: economics improve, provability
collapses, provability binds. COT's 40-year history still only reaches
eff/bar 0.51. **Positioning and OI data cannot carry a primary hypothesis
at this account's scale.** They enter as conditioners or not at all.

> **[§54]** The 180m row reproduces the repo's measured anchor exactly (BH bar 1.64 at
> 12,000 units, k=9). Two qualifications: the table's "n (6yr)" understates non-micro
> observables, which have 16 years (4,125 spliced sessions); and every "n" in this document
> that counts bars rather than sessions repeats the unit error §45 corrected.

### The retail-is-dumb premise is weaker than the programme has assumed

Boehmer et al. (2021) find US retail order flow is contrarian *and*
informed — retail imbalance predicts the cross-section of returns
positively for up to 8 weeks — and they explicitly **fail to find that
aggregate retail imbalance predicts market returns.** Aggregate is exactly
the level MNQ/NQ operates at.

Trade-size-as-retail-proxy is also contested: Hund et al. (2025) find size
thresholds separate informed from uninformed poorly, and Easley et al. note
order splitting is the norm in futures, so institutions manufacture
small-lot prints.

This does not kill the class. It means **"retail participation is elevated"
must be registered as a claim about noise and liquidity conditions, not as
a claim that retail is wrong.** Any entry whose S1 rests on "retail loses"
should say why it survives Boehmer.

---

## Class A — participation composition (data already on disk)

### P01 — micro-share extreme reversion
**Observable.** MNQ volume / (MNQ+NQ) volume, per 5m bar.
**S1.** §48 measured this persists at 1.44 bars detrended, ~6× the basis's
0.25, because nothing arbitrages a participation measure. Elevated micro
share means a larger share of flow is small, uninformed, and
liquidity-taking, so price moves formed under it carry less information and
revert more.
**Post-Boehmer framing.** The claim is about *information content of the
move*, not about retail being wrong. Register it that way.
**Data.** On hand.
**n.** High — every bar qualifies, condition on quantile.
**Risk.** The 0.292→0.822 adoption trend. Detrend on time-of-day and yearly
mean as §48 did, or the signal is an adoption clock.

> **[§54] SAMPLE BOUND — part of the entry, not only a risk.** MNQ launched 2019-05-06, so
> micro share cannot be computed before it. The usable sample is **~7.3 years, 2,246
> sessions with both contracts trading** — not sixteen. Within that, share rose from 0.292
> to 0.822, so the adoption curve dominates much of what remains even after detrending.
> **"n: High" is wrong on two counts:** the bar count is the wrong unit (§45), and the state
> is session-persistent (session-level phi 0.95, §47), so top-quantile bars cluster into
> whole sessions. Expected effective units **~1,100-1,800**, BH bar **~4.2-5.4 bps**.

### P02 — spread-share contamination conditioner
**Observable.** Calendar-spread volume / total volume, from the **672
spread files already on disk and never used.**
**S1.** When spread volume is elevated, participants are rolling and
managing carry rather than expressing direction. Outright prints during
those windows are partly mechanical. A directional signal should work worse
there — and the same signal conditioned on low spread share should be
cleaner.
**Why it earns a slot.** It is the only observable here that costs nothing,
uses data already paid for, and tests a *contamination* claim rather than an
edge claim. It also identifies roll windows precisely, which the scale
finding (§52) says matters.
**Data.** On hand, unused.
**n.** High.

> **[§54] VALUE IS CONTINGENT, and the data is not yet usable.** A contamination conditioner
> improves a *primary* hypothesis. **All four series are closed; there is no live primary to
> improve**, so its stated benefit is not currently available and it should not be ranked
> first on it. Kept, with that stated. Separately: the 672 spread series exist only as raw
> `.csv.zst` — `parse.py` **discarded them** before parquet, so "on hand" requires a parse
> change first. Its magnitude cannot be predicted in isolation: it is a differential on a
> primary that does not exist.

### P03 — thin-move reversion (Amihud-style)
**Observable.** |price change| per unit volume, per bar.
**S1.** A move achieved on little volume moved a thin book rather than
absorbing informed flow. The loser is whoever crossed a thin book without
information; they keep doing it because order size is chosen from account
size, not from book depth. Grounded in Amihud (2002) and Kyle's lambda.
**Data.** On hand.
**n.** High.
**Risk.** Strongly time-of-day dependent — must be conditioned on the
time-of-day volume norm or the open and the close dominate every firing.
**Scale note.** Ratio-form observable, so §52's check passes natively.

> **[§54] THE SCALE NOTE IS WRONG.** The observable is bps *per contract*, and the contract
> count is not stationary: the spliced series switches from NQ to MNQ on 2019-05-31, and MNQ
> is one tenth the notional. Measured on disk: median 1m bar volume falls from 83-140 (NQ,
> Mar-May 2019) to 26-39 (MNQ, Jun-Jul 2019), so the ratio steps UP ~3-5x at the splice, and
> it then trends inside each segment (median bar volume 16 in 2010, 784 in 2026). **The
> threshold must be relative to a trailing same-contract volume norm (and time-of-day), or
> use NQ-only volume for the whole sample** (`NQ.parquet` spans 2010-2026). Ratio form is
> not scale invariance.

### P04 — overnight/RTH volume-share regime
**Observable.** Globex-session volume share vs its trailing norm.
**S1.** Sessions where an unusual share of volume printed overnight were
driven by non-US flow into thinner books. RTH liquidity arriving should
correct part of it.
**Data.** On hand.
**n.** Once per session — **n ≈ 1,500, bar ≈ 4.6 bps.** Above anything the
programme has observed. Register only as a conditioner.

> **[§54]** The spliced sample has 4,125 sessions, not ~1,500; but an extreme-share
> condition fires on a fraction of them (quartile to decile: ~800-2,100 units), and at an
> RTH-length hold the bar is **~5.8-9.2 bps**. The conclusion stands: conditioner, and
> therefore contingent on a primary like P02.

---

## Class B — order flow (requires a Databento purchase)

Needs `tbbo` or `trades` on GLBX.MDP3. This is the largest genuinely new
information class available, and the only one that gives **signed** flow.

### P05 — order-flow-imbalance divergence
**Observable.** Signed volume (aggressor side) per bar vs price change.
**S1.** When price rises while signed flow is negative, the move is book
thinning rather than buying pressure — mechanically driven, so it should
revert. When price and flow agree, the move is absorbed and should persist.
This is the cleanest "who is on the other side" test available.
**Data.** `tbbo`, purchase required.
**n.** Very high.
**Note.** OFI is well mined by HFT at sub-second horizons. At 5–180m it is
much less so. Register with that stated, not assumed away.

### P06 — flow-imbalance persistence asymmetry
**Observable.** Autocorrelation of signed flow, conditioned on regime.
**S1.** Informed flow is split across time and therefore persists;
uninformed flow arrives at once and does not. Persistence of imbalance is
thus a real-time informativeness proxy.
**Data.** `tbbo`.
**n.** Very high.

> **[§54] NOT YET A HYPOTHESIS.** It names an observable and an interpretation but no trade:
> no entry condition, direction or hold. A magnitude cannot be predicted for something with
> no trade rule, so it cannot pass the S2 magnitude check as written.

### P07 — small-lot volume share
**Observable.** Share of volume in 1–2 lot trades.
**S1.** Same class as P01 but within one instrument, so no cross-contract
arbitrage confound and no adoption trend.
**Contested — flag prominently.** Hund et al. (2025) and the order-splitting
literature both undercut size-as-retail. Register the observable as
"small-lot share," never as "retail share," and state that the
interpretation is not established.
**Data.** `trades`.
**n.** Very high.

> **[§54]** Confirmed purchase-dependent: the `trades` column in the parquet is 100% null, so
> no volume-per-trade proxy exists on disk.

---

## Class C — positioning (conditioners only, per the horizon table)

### P08 — open-interest exhaustion
**Observable.** Daily OI change vs price change.
**S1.** Price move with falling OI is position closing — forced or
capitulating, and price-insensitive, so it overshoots. Price move with
rising OI is new positioning, which is discretionary. The classic
four-quadrant framework.
**Data.** Databento `statistics` schema (cheap) or CME daily files (free).
**n.** ~1,500 daily. **Bar ≈ 9.3 bps.** Cannot be a primary hypothesis.
Register as a conditioner on P01/P03/P05.
**Also.** This framework is widely published in retail trading material,
which is a mark against it on crowding grounds and should be recorded.

### P09 — COT non-reportable extreme, MGC only
**Observable.** CFTC non-reportable net position, weekly.
**S1.** Hedging-pressure literature finds effects across futures markets
but describes evidence in **financial** futures as inconclusive. Gold is a
commodity, where the evidence is stronger. So this is registrable on MGC and
not on MNQ/MES.
**Data.** Free from CFTC, ~40 years.
**n.** 2,080 weekly. **eff/bar 0.51** — below the bar even with four decades.
Economics-only, significance limb waived at registration, or not at all.

> **[§54] THE 40 YEARS ARE NOT AVAILABLE.** COT history is ~40 years, but a return needs a
> price series, and **GC is not on disk**. The tradeable MGC series starts 2010: ~830 weeks,
> and an extreme-position condition fires on a fraction of those. The bar is far above any
> plausible magnitude, and with that few units even the economic estimate is too wide to
> conclude "worth having", so the economics-only waiver does not rescue it either (N10's
> reasoning, §45).

---

## Class D — structural

### P10 — roll-window exclusion
**Observable.** Days within the roll window, identified by spread-volume
spike (P02's machinery).
**S1.** Not an edge claim. A test of whether excluding roll windows improves
every other hypothesis. The R02 post-mortem found roll misalignment carried
99.7% of squared basis in 0.4% of sessions.
**Data.** On hand.
**Value.** Cheap, and it is the kind of contamination that has already
inverted one verdict in this programme.

> **[§54]** Same contingency and data status as P02: no live primary to improve, and the
> spread files need a parse change.

### P11 — release-window flow buildup
**Observable.** Volume and (if purchased) signed flow in the 30m before
scheduled 08:30/10:00 ET releases.
**S1.** Positioning ahead of a scheduled release is discretionary and
directional; the pre-release book is thin because market makers widen.
**n.** ~800 events. Marginal, same class as N10. Economics-only or defer.

### P12 — cross-product participation divergence
**Observable.** MNQ micro-share vs MGC micro-share, both detrended.
**S1.** When retail-share spikes in one product and not the other, the spike
is product-specific attention rather than a market-wide liquidity regime.
Separates "attention" from "conditions," which P01 alone cannot.
**Data.** On hand (MGC/MNQ; note MGC micro-share needs GC, which is **not**
on disk — check before assuming).
**n.** High.

> **[§54] CHECKED: GC IS NOT ON DISK.** The batch holds MNQ, NQ and MGC only, so MGC micro
> share cannot be computed and the entry cannot proceed without a purchase. It also specifies
> no trade rule, so no magnitude can be predicted.

### P13 — volume-concentration shape
**Observable.** Herfindahl of volume across minutes within a session, vs its
trailing norm.
**S1.** Concentrated volume means the session was event-driven; dispersed
volume means continuous two-sided trading. A move formed in a concentrated
session is more likely a single participant's footprint.
**Data.** On hand.
**n.** Once per session — conditioner only.

---

## Recommended order

> **[§54] SUPERSEDED by the magnitude-based order in `decisions.md` §54.** The draft's order
> is kept below for the record.

**Register first, no purchase needed:** P02, P03, P01.
P02 because it uses data already bought and tests contamination rather than
edge; P03 because its mechanism is the best-documented in the list and it is
natively scale-invariant; P01 because §48 already measured its persistence.

**Then, if a purchase is justified:** P05, then P06. Signed flow is the only
genuinely new information class here, and P05's "price up, flow negative"
test is the sharpest non-price question available.

**Conditioners, never primaries:** P04, P08, P13.

**Economics-only or defer:** P09, P11.

**Register with the interpretation caveat stated:** P07.

**Do not register yet:** P10 and P12 are useful measurements, not
hypotheses — P10 is a contamination check, P12 needs GC data confirmed on
disk first.

---

## Standing requirements

- S2 magnitude, checked against the BH bar at expected n (§45/§50).
- S2 scale invariance — thresholds in bps, volatility or ATR units (§52).
  Most of this list is ratio-form and passes natively; P03 and P05 need care.
- S5 variance gate before any S6 placebo (§46 ordering error).
- S6 placebo must be matched at `valid_from`, measuring reachability (§49).
  Note these are **state conditions, not levels** — the level-based placebo
  construction may not transfer at all. Establish the placebo design for a
  state observable before registering any of them; that is the single
  largest open methodological question in this list.

> **[§54] SETTLED IN PART.** See §54 "Control design": the location-based placebo is a
> category error for state conditions; the chance-alignment null already exists inside every
> S7 run as the rotation null; the confound-matched control is the part that remains open.
