# P03 — thin-move reversion, S7

**Verdict: RETIRED at S7 on its pre-registered clause.** One cell, one trial. N 759 → **760**,
SR\* **0.1368**, chain verified. Registry: `hypotheses.yaml` P03. Decision record:
`decisions.md` §58.

| | |
|---|---|
| real − control | **+0.0794 bps** |
| pre-registered threshold | **+0.625 bps** — misses by **7.9×** |
| real leg, gross | +0.2004 bps |
| real leg, **net of the 0.48 bps floor** | **−0.2796 bps** |
| separated | no — CI [−0.302, +0.451], p = 0.691 |
| pairs | 24,781 |
| implied reversion fraction | **0.86%** of the measured excess, against 6.8% required |

---

## What was pre-registered, before the run

**The threshold.** P03 clears iff more than **6.8%** of the measured **9.18 bps** excess
displacement reverts within 15 minutes — that is, real − control above **+0.625 bps**.

**The prior was unknown, not high.** The 9.18 bps is a *ceiling*: no reversion returns more
than the move that was made, and an unknown part of it is permanent information rather than
transitory impact. **A null is informative here because the threshold is low, not because the
effect was expected.**

**The binding constraint is economics, not significance.** Cost floor 0.48 bps against a BH
bar of 0.463–0.625. Every earlier P-series entry was significance-dominated — P01 needed
4.2–5.4 bps, P09 needed 72–102 — so a null at P03 says the effect is **small in bps**, not
that the test could not see it. This was recorded before the result, not after.

## S5 — the gate, run first

**PASS.** Entry-minute sd **110.2** over a 380-minute spread, so the condition is not firing
at a fixed minute. Neighbouring thresholds change *which* bars fire rather than merely how
many: Q85 selects 40,902 events at Jaccard **0.67** against the registered set, Q95 selects
13,737 at **0.50**. Directional collapse is N/A by construction — P03 has no level set
carrying a high and a low, and a bar has one signed return.

## S6 — the matched state control, `bar` mode

**MATCHED.** 27,437 of 27,437 firings paired, 25,525 distinct control bars, **7.0% reuse**.

| time-of-day dev | volatility dev | year dev | era fallback |
|---|---|---|---|
| 0.000 | 0.000 | 0.000 | 0.0% |

Bar mode was forced, not chosen: the state fires 7.71 times per session and touches 92.6% of
sessions, so strict mode's clean pool does not exist (§55). Its contamination costs power, not
validity — recorded before the run, and it pushes the same way as the horizon limitation below.

## S7 — economics first, separation second

    real leg gross            +0.2004 bps
    real leg net of cost      -0.2796 bps      <- loses money before significance matters
    control leg gross         +0.1209 bps
    REAL - CONTROL            +0.0794 bps
    pre-registered threshold  +0.625  bps      -> DOES NOT CLEAR
    per-trade Sharpe (real)    0.0078

    CI [-0.3022, +0.4510]   p = 0.6910   separated: False

**The economics limb refutes on its own and needs no power argument.** The real leg is negative
net of cost, so the trade loses money whatever the p-value does. That is the L12 shape (§45):
the refutation rests on magnitude and economics.

## S8 — era split, by default (§53)

| era | n | real | control | diff | CI | p |
|---|---|---|---|---|---|---|
| early | 12,399 | +0.0088 | −0.0053 | +0.0140 | [−0.395, +0.413] | 0.948 |
| late | 12,382 | +0.3922 | +0.2473 | +0.1449 | [−0.496, +0.781] | 0.686 |

**No sign flip and no decay.** Both halves are positive, tiny and insignificant, and both are
far below the threshold. Unlike N02 — whose point thresholds ran a different trade in each era —
P03's threshold is a rank and runs the same trade throughout, so the split is interpretable and
it says the null is uniform rather than era-specific.

## The null was fault-injected before it was believed

§46 says to look for the bug when something clears. **The mirror risk needed the same
treatment**: a null manufactured by a sign error or an off-by-one in the hold looks exactly
like a real one. `tests/test_p03_outcomes.py` pins four properties of the outcome path:

- a **known injected reversion of +4.0 bps is recovered as +3.45** — right sign, right size;
- the same path on a pure random walk returns zero within noise, so the test above cannot pass
  on a constant;
- the hold never crosses a session boundary, so no overnight gap is spliced in;
- a move that *extends* costs the fade rule money, pinning the sign convention.

The machinery could have seen an effect seven times smaller than the one it was looking for.
**The null is a measurement, not an artifact.**

## What this does and does not settle

**Settled.** At a 15-minute hold, fading a thin move returns 0.86% of the excess displacement
it creates — against the 6.8% needed to pay for itself. The effect is real in sign and far too
small in size, and it is negative net of cost.

**Not settled, and recorded before the run rather than offered afterwards.** The state's own
decay half-life is **3.5 minutes**, and **H = 15 is the shortest horizon the grid carries**, so
this test sits ~4 half-lives past the mechanism's clock. A null there is weak evidence about
thin-move reversion *at its own timescale*. Re-testing shorter would be a **new registration
with its own trial**, not a re-reading of this one — R01's rule, r-series §17. Bar mode's
contamination pushes the same way.
