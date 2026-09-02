# F14 - timestamp_hash_control, Stage 1

Run by `python -m futuresres.signals.f14`. CLAUDE_FUTURES.md §7.6.

## PASS - the control did not separate

**0 BH survivors on either instrument.** The harness declines to promote a signal that cannot relate to future returns by construction, on real futures data with real gaps, real volatility clustering and real session boundaries.

## The condition, as registered

| | |
|---|---|
| signal | low bit of SHA-256 of the bar's ISO timestamp |
| fires | each 30-minute RTH slot open, 09:30-15:30 ET (13 a session) |
| holds | 30, 60, 120 minutes |
| free parameters | **none** (`param_cap: 0`) |

The premise is that this signal **cannot** relate to future returns, not that it *should* not - the distinction that retired F11. The direction is a deterministic function of the clock, never of price, and any single value can be recomputed from the timestamp to confirm it.

## Results

| instrument | hold | events | long share | mean bps | net bps | Sharpe | p | floor bps |
|---|---|---|---|---|---|---|---|---|
| MGC | 30m | 51,753 | 0.497 | -0.03 | -0.68 | -0.0018 | 0.7693 | 4.17 |
| MGC | 60m | 51,753 | 0.497 | -0.11 | -0.76 | -0.0045 | 0.4952 | 4.17 |
| MGC | 120m | 51,753 | 0.497 | -0.11 | -0.76 | -0.0034 | 0.6510 | 14.34 |
| MNQ | 30m | 47,866 | 0.497 | -0.00 | -0.48 | -0.0002 | 0.9902 | 2.57 |
| MNQ | 60m | 47,866 | 0.497 | +0.10 | -0.38 | +0.0027 | 0.6170 | 2.57 |
| MNQ | 120m | 47,866 | 0.497 | +0.07 | -0.41 | +0.0015 | 0.7827 | 15.66 |

## Multiplicity

| instrument | cells | nominal separations | expected by chance | BH survivors |
|---|---|---|---|---|
| MGC | 3 | 0 | 0.15 | **0** |
| MNQ | 3 | 0 | 0.15 | **0** |
| **both** | 6 | 0 | 0.30 | **0** |

Six cells is a small grid, and deliberately so: a control with no free parameters has nothing to sweep. Expected-by-chance is correspondingly small (0.30 across both instruments), which means a single nominal separation would already be notable here in a way it would not be in a 117-cell hypothesis.

## Aggregate

| instrument | aggregate bps | net of cost | cost floor |
|---|---|---|---|
| MGC | -0.08 | **-0.73** | 0.65 |
| MNQ | +0.06 | **-0.42** | 0.48 |

## Data

| instrument | sessions | 09:30-17:40 ET minutes traded |
|---|---|---|
| MGC | 3,981 | 63.28% |
| MNQ | 3,682 | 83.46% |

Event counts exceed the 45,513 and 38,494 estimated at registration, and that is expected. `reports/control_candidates.md` measured firings by requiring a **traded** bar at the exact slot minute, giving 9.2 a session on MNQ. The pipeline reindexes each session to a complete minute grid and forward-fills, exactly as F03 and F04 do, so all 13 slot opens exist and the condition fires at every one - which is what the registered condition says. The registration figure was a conservative lower bound on the same quantity; more events, not fewer, so resolvability is unaffected.

The timestamp a position hashes is built from the **calendar**, not from the bar, so a forward-filled minute hashes identically to a traded one. Had the hash been taken from the bar's own recorded timestamp, a filled minute would have inherited the previous trade's stamp and the direction would have become a function of trading activity - which is a property of the market, and would have quietly made the control a hypothesis.

## Scope of what this licenses

**F03-like event counts only.** F14 reaches ~45,000-53,000 events. It demonstrates that the harness declines to promote a mechanism-free signal at that sample size on real data. It demonstrates **nothing** about ~4,000-event samples.

**F01, F02, F04, F06 and F09 have no real-data control and cannot get one.** A once-a-session condition over sixteen years yields ~3,500 events against MNQ's 19,722 - a property of the sample, not of any signal. A null from any of those five must say so rather than borrowing this result's assurance. The synthetic GARCH nulls of §7.2 are the only check that reaches that regime, and they test idealised noise rather than real microstructure.
