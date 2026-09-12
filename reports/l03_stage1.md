# L03 Stage 1 - prior-day sweep and reclaim, against matched placebo regions

**Verdict: null. 0 of 18 cells separate against 0.90 expected by chance.** 18 trials spent.

Every figure is **(real level) minus (matched placebo region)**, MGC only, **H=180
pre-registered as the sole horizon**, cost floor **0.65 bps**. Trials were logged BEFORE the
run. The condition is sweep-and-reclaim: price exceeds the level by >= m ticks then closes
back inside within k bars, traded **counter to the penetration**.

**The control is weaker than a displaced level** (`decisions.md` 37). It equalises where a
region sits and how often price reaches it, and **nothing about how price arrived**. A
difference here means "behaves differently from an equally-reachable arbitrary region",
which is weaker than "behaves differently given the same approach".

## Results

Range **-2.007 to +2.404 bps** across `prior_rth` and `prior_full`. Best cell
`prior_full m=4 k=2` at **+2.404 bps,
p=0.1145** - nominally the largest in the run and
still not separated.

| level type | m | k | n | real | placebo | diff | CI | p | sep |
|---|---|---|---|---|---|---|---|---|---|
| prior_full | 4 | 2 | 1,699 | -0.343 | -2.747 | **+2.404** | [-0.61, +5.52] | 0.1145 | - |
| prior_full | 4 | 3 | 1,735 | -0.303 | -2.176 | **+1.873** | [-0.98, +4.78] | 0.2185 | - |
| prior_full | 4 | 5 | 1,763 | -0.003 | -1.493 | **+1.490** | [-1.50, +4.36] | 0.3315 | - |
| prior_full | 2 | 2 | 1,775 | +0.377 | -0.975 | **+1.352** | [-1.35, +4.27] | 0.3710 | - |
| prior_full | 2 | 5 | 1,794 | +0.089 | -1.103 | **+1.192** | [-1.63, +3.82] | 0.4275 | - |
| prior_full | 2 | 3 | 1,786 | +0.199 | -0.992 | **+1.191** | [-1.70, +3.88] | 0.4335 | - |
| prior_full | 8 | 3 | 1,512 | -1.180 | -2.126 | **+0.945** | [-2.61, +4.45] | 0.5890 | - |
| prior_full | 8 | 2 | 1,375 | -1.560 | -2.210 | **+0.649** | [-3.12, +4.56] | 0.7215 | - |
| prior_full | 8 | 5 | 1,620 | -0.901 | -1.115 | **+0.214** | [-2.91, +3.31] | 0.8940 | - |
| prior_rth | 2 | 3 | 2,860 | -0.892 | -0.924 | **+0.033** | [-1.97, +2.14] | 0.9730 | - |
| prior_rth | 2 | 5 | 2,867 | -1.018 | -0.908 | **-0.110** | [-2.08, +1.96] | 0.9065 | - |
| prior_rth | 2 | 2 | 2,842 | -1.147 | -0.953 | **-0.193** | [-2.24, +1.93] | 0.8600 | - |
| prior_rth | 8 | 5 | 2,543 | -1.792 | -1.447 | **-0.345** | [-2.60, +1.86] | 0.7850 | - |
| prior_rth | 4 | 3 | 2,777 | -1.224 | -0.785 | **-0.439** | [-2.54, +1.74] | 0.6850 | - |
| prior_rth | 4 | 5 | 2,832 | -1.137 | -0.633 | **-0.503** | [-2.54, +1.55] | 0.6230 | - |
| prior_rth | 4 | 2 | 2,697 | -1.433 | -0.907 | **-0.526** | [-2.64, +1.71] | 0.6205 | - |
| prior_rth | 8 | 3 | 2,354 | -2.252 | -0.669 | **-1.582** | [-4.08, +0.84] | 0.1945 | - |
| prior_rth | 8 | 2 | 2,143 | -2.190 | -0.183 | **-2.007** | [-4.63, +0.84] | 0.1580 | - |

## Reading

**Nothing separates**, and unlike L02 the mechanism here is not instrument-specific: prior-day
extremes as reference prices is not an equity story, so MGC is a legitimate test of the
registered claim. MGC-only is an event-count constraint alone - MNQ's best cell sits at 3,762
against a 5,884 floor, 0.64x.

Both level types matched their placebo (`decisions.md` 37), so no cell was excluded.

Events 1,699-4,679 per cell against a 2,862 floor. The larger cells had adequate power; the
smallest did not, and the entry records which.

**This is the stronger of the two nulls.** L02's mechanism was never exposed; L03's was, on an
instrument where it should hold, and produced nothing.

**Status: retired.**
