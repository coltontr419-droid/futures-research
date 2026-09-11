# Checkpoint — L02/L03/L04 Stage 1 complete, 2026-09-11

Written at a hard stop. **All three runs FINISHED. 63 trials spent and logged.
N = 684 → 747, chain verified. SR\* 0.1356 → 0.1365.**

Nothing is in flight. `trials.jsonl` L02=27, L03=18, L04=18, L07=108.

## THE OWED WORK, and it is owed BEFORE any write-up

**L04 came back positive and the bug hunt has NOT been run.** This was pre-committed in
`decisions.md` 42 — *"If anything clears, look for the bug before writing it up"* — and it is
the next action. Do not write `reports/l04_stage1.md` first.

## Results

Cells are in `reports/l02_cells.json`, `l03_cells.json`, `l04_cells.json`. Every figure is
**(real level) minus (matched placebo region)**, MGC, H=180, cost floor **0.65 bps**.

| | live cells | excluded | separated | expected by chance | BH survivors | diff range |
|---|---|---|---|---|---|---|
| L02 absorption | 27 | 0 | **0** | 1.35 | 0 | −0.62 .. +1.84 |
| L03 | 18 | 0 | **0** | 0.90 | 0 | −2.01 .. +2.40 |
| L04 | 18 | 9 | **5** | 0.90 | **0** | −1.38 .. +3.54 |

**L02 and L03 are clean nulls** — zero separations against 1.35 and 0.90 expected.

**L04 is not.** Five of eighteen separate against 0.90 expected, ALL of them `sess_Asia`,
and **none survives BH within the hypothesis**:

| level type | m | k | n | real | placebo | diff | CI | p | ×cost |
|---|---|---|---|---|---|---|---|---|---|
| sess_Asia | 8 | 2 | 2,715 | +0.538 | −3.006 | **+3.544** | [+1.120, +5.998] | 0.0045 | **5.5×** |
| sess_Asia | 4 | 2 | 3,393 | −0.175 | −2.702 | +2.527 | [+0.562, +4.405] | 0.0135 | 3.9× |
| sess_Asia | 4 | 3 | 3,484 | −0.111 | −2.476 | +2.366 | [+0.533, +4.323] | 0.0125 | 3.6× |
| sess_Asia | 8 | 3 | 3,007 | +0.009 | −2.218 | +2.227 | [+0.064, +4.349] | 0.0495 | 3.4× |
| sess_Asia | 4 | 5 | 3,523 | −0.277 | −2.407 | +2.131 | [+0.298, +4.030] | 0.0175 | 3.3× |

`sess_Asia` 5/9 separated, diff +1.33..+3.54. `sess_London` **0/9**, diff −1.38..−0.60.
`sess_US` excluded (placebo unmatched, touch ratio 1.33).

### Why this needs a hunt rather than a write-up

**The decomposition is the suspicious part.** The real level earns roughly ZERO (+0.54 down
to −0.28); the entire difference comes from the PLACEBO LOSING 2.2–3.0 bps. That is the same
shape as L07 (38) but with the sign reversed, and it means the claim is not "Asia extremes
pay" — it is "arbitrary regions at a matched distance lose money in the Asia session."

**Specific things to check, in order:**

1. **Is the placebo systematically mispriced in the Asia window?** `sess_Asia` levels become
   valid at minute 541 and the session is thin. If `make_region_placebo` places regions where
   the spread or the fill assumption is different, the placebo leg is measuring
   microstructure, not reaction. **Check the placebo's own touch rate and entry-minute
   distribution inside the Asia window specifically**, not pooled.
2. **Direction mix.** `real_dir_up_share` is 0.50–0.51 for every separating cell, so the real
   side is balanced. **Measure the placebo's** `up` share — if it is skewed, the difference is
   drift, not reaction. This is the same open question 38 left for L07 and it is cheap here.
3. **Session-boundary leakage.** Asia levels are valid from 541 and the hold is 180 minutes,
   so an entry after ~1195 truncates at `RTH_EXIT`. Check whether the separating cells
   concentrate in entries whose hold is clipped.
4. **BH already says no.** Zero of five survive correction within the hypothesis. The
   strongest p is 0.0045 against a rank-1 BH threshold of 0.05/18 = 0.00278. **The honest
   headline is that nothing survives**, and the hunt is about whether even the nominal
   pattern is real.
5. **L02/L03 nulls make an Asia-only positive more suspicious, not less.** The same
   condition, same placebo construction and same instrument produced nothing at opening-range
   or prior-day levels.

## Interpretation constraints already recorded — read before writing

- **`decisions.md` 42, written BEFORE the run**: L02 is MGC-only by necessity, 09:30 ET is
  the equity cash open against gold's 08:20 COMEX, so **a positive would not support the
  registered mechanism and must not be reinterpreted as cross-asset spillover afterwards.**
  L02 came back null, so this binds less than it might have — but the same logic applies to
  any post-hoc story for L04's Asia result.
- **`decisions.md` 41**: L02's sweep arm is withdrawn; only absorption ran. L05 is noted
  defective. A corrected sweep is a NEW registration, not an inherited slot.
- **`decisions.md` 37**: the control is WEAKER than a displaced level — it equalises where a
  region sits and how often price reaches it, and nothing about how price ARRIVED. Any L04
  result must be written in those words.

## State

- Working tree clean at the commit carrying this file; everything pushed.
- **N = 747, SR\* = 0.1365.** `measurements.jsonl` unchanged.
- Data intact: `data/continuous/` holds MGC, MNQ, NQ and NQ_MNQ_spliced. Rebuild verified by
  byte-identical reproduction of `batch_contents.md` and `splice.md` and by every L01–L10
  firing rate returning unchanged.
- `./progress.sh` reports any running job (pid, RSS, elapsed), memory, logs, parquets, OOMs.

## To resume

1. **Run the L04 bug hunt above. Do not write the report first.**
2. Then `reports/l02_stage1.md`, `l03_stage1.md`, `l04_stage1.md`, registry outcomes,
   `decisions.md` 43.
3. Then the L-series closeout: L10 is the ONLY open (disjoint) route in the catalogue at
   1%/5% against 97–100% for everything else (41), which is why every hypothesis resolves on
   per-cell counts.
4. Still open and NOT blocking: L07's direction-mix asymmetry (38), the `d` ATR reference
   period for L01/L06/L08 (frozen, a specification change and not settleable by measurement).
