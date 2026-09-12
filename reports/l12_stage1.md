# L12 — Asia-session reclaim on MNQ, out of sample

> **Stages: S7 (multiplicity) and S8 (out-of-sample, economics).** Cleared S1–S6. See
> `reports/STAGES.md`.

**Verdict: retired at S7, ON ECONOMICS. 0 of 9 cells separate; mean difference +0.306 bps
against a 0.48 bps cost floor — 0.64×, and 4–11× short of its own registered magnitude.**

9 trials spent. **N 747 → 756, SR\* 0.1368**, chain verified.

## What this test was for

L04 tested three session types on MGC. `sess_Asia` gave 5 of 18 nominal separations and
`sess_London` none, so Asia was **selected by its result** (§43). Selection by result is not
repaired by re-testing the survivor on the same data — §38 refused that for L07's mirror and
§43 refused it here. It is repaired by testing the selected claim on data that did not
generate it. **MNQ is that data, and MGC was deliberately excluded.**

The prediction was registered before the run: positive, **+1.3 to +3.5 bps**, confirming only
on a positive mean **and** at least one BH survivor at FDR 0.05.

## Results

Mean **+0.306 bps**, positive in 8 of 9 cells, range −0.281 to +0.577, **smallest p 0.5810**.

| m | k | n | real | placebo | diff | CI | p |
|---|---|---|---|---|---|---|---|
| 4 | 3 | 4,052 | -3.208 | -3.785 | **+0.577** | [-1.40, +2.45] | 0.5810 |
| 2 | 5 | 4,118 | -2.812 | -3.337 | **+0.524** | [-1.28, +2.40] | 0.5970 |
| 8 | 2 | 3,548 | -2.638 | -3.135 | **+0.497** | [-1.92, +2.94] | 0.6555 |
| 4 | 5 | 4,091 | -3.035 | -3.514 | **+0.479** | [-1.40, +2.40] | 0.6370 |
| 8 | 5 | 3,927 | -3.111 | -3.563 | **+0.452** | [-1.54, +2.61] | 0.6730 |
| 2 | 3 | 4,113 | -3.050 | -3.309 | **+0.259** | [-1.65, +2.34] | 0.7920 |
| 4 | 2 | 3,995 | -3.376 | -3.574 | **+0.197** | [-1.80, +2.24] | 0.8565 |
| 8 | 3 | 3,772 | -3.001 | -3.051 | **+0.050** | [-2.15, +2.29] | 0.9555 |
| 2 | 2 | 4,095 | -3.350 | -3.069 | **-0.281** | [-2.23, +1.64] | 0.7640 |

## THE REFUTATION DOES NOT REST ON THE P-VALUES

It would be wrong to cite p=0.5810 as refutation, and the reason is an S4 argument that was
checked only after the run.

**The tabulated S4 floor does not apply here.** MNQ/180m is 15.66 bps, measured at n=5,884 —
essentially this test's n — but it is defined as the *smallest injected effect promoted
end-to-end at ≥80%* for a slow regime flipping every ~500 bars. That is a far harder
detection problem than a paired mean difference, and §38 decision 4 already established these
figures are not the bar for a real-minus-placebo test.

**The applicable bar is this test's own bootstrap: median SE = 1.016 bps.** A BH rank-1
survivor (p < 0.00556 across 9 tests) requires **|effect| > 2.82 bps**.

| true effect | P(BH survivor) |
|---|---|
| 1.3 bps — bottom of the registered range | **6.8%** |
| 2.0 bps | 21.1% |
| 2.82 bps — the bar | 50.1% |
| 3.5 bps — top of the registered range | 74.9% |
| 3.54 bps — L04's MGC point estimate | **76.2%** |

**So the significance limb was satisfiable only in the top fifth of the registered range.**
Across the lower ~80% a survivor was effectively unreachable. That is a pre-registration
defect: a prediction whose lower four-fifths cannot produce the required outcome can
essentially only fail. It was not noticed before the run. §45 records it and proposes a
standing S2 check.

**The magnitude and economics limbs need no power argument, and they are what this rests on:**

| | |
|---|---|
| delivered | **+0.306 bps** |
| registered range | +1.3 to +3.5 bps → **4–11× short** |
| MNQ cost floor, round trip | 0.48 bps |
| delivered / cost | **0.64× — not tradeable** |

## What it does and does not settle about L04

**Does settle:** L12 had **76.2% power** against L04's +3.54 bps point estimate — close to
the conventional 80% — and delivered **+0.306**, about 9% of it. That is a genuine failure of
*that magnitude* to replicate on an independent instrument.

**Does not settle:** whether a smaller but real effect exists. Power was 7–21% across the
lower half of the registered range, so this test cannot speak to a 1–2 bps effect either way.

**An earlier draft of this report over-claimed** that an independent instrument shows BH was
right rather than merely conservative on L04. That is too strong and is withdrawn. The
accurate statement is narrower and more interesting: **both hypotheses were operating at the
edge of their resolution.** L04's observed +3.54 bps sat *below its own* BH rank-1 bar of 3.72
bps (SE 1.244, 18 tests) — no survivor was reachable at its observed effect size either. The
S7 failure in both cases reflects resolution at the edge as much as multiplicity correction.

## The decomposition, which is the informative part

On MNQ **both legs lose heavily**: real −2.6 to −3.4 bps, placebo −3.0 to −3.8. The
difference is a small gap between two losing trades.

On MGC the real leg was near zero (+0.54) while the placebo lost 3.0. **That pattern does not
reproduce.** What reproduces is only the weak ordering that the real level loses slightly
less — and at 0.64× the cost floor that ordering is not worth anything.

## Standing caveat, recorded before the run

L12's independent event count is 4,933–4,967 against the tabulated 5,884, so it is short at
S4 as registered. That caveat cuts the same way as everything above: it is a reason this test
cannot license a positive claim about small effects, not a reason to discount the economics.
