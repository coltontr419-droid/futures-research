# Next miner — gap list vs UID 252, build, test schedule, withdrawal (11-13 PM, §1440)

## Prerequisites 1–4 (done)
| # | Item | Status |
|---|---|---|
| 1 | **Presence (soft pacing)** — we quoted on ≈ 25 books vs 252's ≈ 192: at-the-touch quotes drained each book's 900-s bucket in seconds, then the book went dark. New: `pace_soft=5000 pace_soft_min=0.05` (unit) — sizes shrink as the bucket drains, a book goes dark only below −$5k; live on/off `pace_soft_on`. Flow model: presence 14% → ≈ 100% at the same $/day. Cap attacks all PASS (worst $453–457k; toggling hourly $467k / $492k of $500k). | built 10dc929d |
| 2 | **Fee-aware quoting** — the validator nets 0.005 × maker fee (105–140 bp now) from every maker fill. New live `mk_fee_k`: quotes move k × 0.005 × rate × mid away per side (120 bp on $300 ≈ 2 ticks); jumped sides keep their price. | built, off by default |
| 3 | **Speed** — our answer 0.41 s vs 252's 0.15 s is our compute (network 19 ms). New: per-book config cache (≈ 12% of compute), model skipped when unused (≈ 9%). Measure call_time on the new miner (target ≤ 0.3 s; parallel books = later). | built |
| 4 | **Start budget** — x2's 256-book burst ($100k per never-seen book) lost money and left it at score 0 for its whole protection. New unit: `pace_start=20000`. | unit setting |
Build: /opt/mvtrx/agents/QuoteAgent.next-10dc929d.py (NOT active). test_pace ALL PASS. needrestart exclusion already on the lab (§1430).

## Everything separating us from 252 (deep dive §1428–§1440)
| Gap (us vs 252) | Evidence | Fix | Status |
|---|---|---|---|
| Presence 25 vs 192 books | order_books gauge; 230/256 books paced out | soft pacing | **test T1** |
| Fee netting eats edge (making ≈ 0 field-wide) | Mf 105–140 bp; class credit −95% | mk_fee_k | **test T2** |
| Fills after a favourable fundamental move 8% vs 44%; 2-min markout −0.4 vs +0.8 bp | fundmove256 | rest behind + step in (lean-only + jump 3) — first try was blind (no presence) | **test T3** |
| $30 edge +2.9 vs +3.9 bp on 1.7× the volume | profile | $30 touch only at ≥ 2-tick spreads | **test T4** (never run) |
| Inventory held ≈ 0.55× theirs ($2.6k vs $4.6k per book) | profile | skew 3 vs 5 | **test T5** (never run) |
| $300 fills one tick back 17–22% vs 7–10%; avg fill $1.0k vs $2.2k | profile | ladder "2:5" vs "1:2:4:7" | **test T6** (never run on 256 books) |
| Inside the spread 14% vs 34% | profile | inside 2 vs 3 | **test T7** (only bundled before) |
| Response time 0.41 vs 0.15 s | call_time | speed build | measure at start |
| Start burst / protection-end death | §1416/§1439 | pace_start 20k; positive score by ≈ T+12 h | unit |
| 4-dec: 252 does not quote them | profile | keep ours (credit ≈ 10× per unit once fees fall; no pay effect now) | no test |
**PROVEN 11-13 (T1 interim, UID 174): soft pacing = the presence fix** — on ≈ 113 books with resting orders vs off 5 books (248/256 paced). Registry: memory mvtrx-proven-results.md.
**PROVEN 11-13 (T2, UID 174): fee-aware quoting mk_fee_k 1.0** — presence +39%, $300 edge per $ ≈ 2×, pay-weighted edge +17%, skill tie; adopted live.
Already PROVEN (not re-tested): $300 size 0.044 + inside 3 + lean 1.0 (skill +0.36/+0.20/+0.42), $30 shape (+23–25% edge $), 4-dec touch kept, 4-dec size/deep ties.

## Starting settings (proven base)
Unit: agent 10dc929d, pace_cap 450000, pace_steady 450000, **pace_start 20000, pace_soft 5000, pace_soft_min 0.05**, tape on, live_params_s 5.
Live: x2's FINAL (§1432) = $300 mk_vol_size 0.044, mk_vol_inside 3, fund_mv 1.0 (cap 2); $30 mk_low_size 0.033, mk_low_lad "1", mk_low_lad_size 0.033; 4-dec touch + deep 0.27, size 0.09; skew 5; **pace_soft_on 1**; mk_fee_k 0.

## Test schedule (T = start; 2-h ABBA, 30-min blocks; per-arm grpcap + skill reads + presence from order_books; reference control vs 252/216)
| Slot | Test (A vs B) | Decides on |
|---|---|---|
| T+0–1 h | none — start, check quoting, presence, call_time | — |
| T1 T+1–3 h | soft pacing on vs off | presence (order_books), skill, making |
| T2 T+3–5 h | mk_fee_k 1.0 vs 0 | $30 / 4-dec making edge after fees, live making |
| T3 T+5–7 h | lean-only + jump 3 vs touch | WITH share, $300 skill net of refs |
| T4 T+7–9 h | $30 touch-min 2 vs 0 | $30 edge per $, edge $, $30 skill |
| T5 T+9–11 h | skew 3 vs 5 | skill, inventory |
| **check T+12 h** | live making and/or skill must be > 0; if not → stop testing, settle on the best-known | survival |
| T6 T+11–13 h | $300 ladder "2:5" vs "1:2:4:7" | $300 skill, avg fill, presence |
| T7 T+13–15 h | inside 2 vs 3 | $300 skill, inside share |
| T8 T+15–17 h | CONFIRMATION: all winners vs base | everything |
| T+17–24 h | settled — no changes (protection ends T+24 h) | — |
Extensions only after T8. No taking. Each test winner decided by: presence → skill net of refs → pay-weighted making.

## Withdraw first (user runs these; one hotkey at a time, MEV protection off, no batch)
Stake on the coldkey now (11-13 ≈ 1 PM): x3 27.48, x1 9.95, x2 2.91, x4 2.77 alpha on subnet 79 (≈ 43.1 alpha ≈ 0.133 TAO at 0.00309), m3 0.021 alpha on subnet 101; free 0.035 TAO.
```
~/btcli/bin/btcli stake remove --wallet.name main --wallet.hotkey x3 --all --no-mev-protection
~/btcli/bin/btcli stake remove --wallet.name main --wallet.hotkey x1 --all --no-mev-protection
~/btcli/bin/btcli stake remove --wallet.name main --wallet.hotkey x2 --all --no-mev-protection
~/btcli/bin/btcli stake remove --wallet.name main --wallet.hotkey x4 --all --no-mev-protection
~/btcli/bin/btcli stake remove --wallet.name main --wallet.hotkey m3 --all --no-mev-protection   # optional: subnet 101 dust
~/btcli/bin/btcli wallet balance --wallet.name main
```
