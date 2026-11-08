# Bittensor mining — full handoff (written 2026-11-08 ≈ 3:15 PM CT)

You are taking over the user's Bittensor mining project from a long previous session. Everything below comes from that session's
records: the memory files in `~/.claude/projects/-home-coltontr419/memory/`, `~/futures-research/reports/decisions.md` (§1164–§1308)
and the live server state. When this file and decisions.md disagree, decisions.md (the newer §) wins.

## 0. FIRST THING TO DO (before anything else)

1. Create `~/futures-research/deploy/sn79/CLAUDE.md` containing the **RULES** section (§1 below) verbatim, plus a short "current
   state" pointer to this file. Work from `~/futures-research/deploy/sn79` so that CLAUDE.md (and the repo's own
   `~/futures-research/CLAUDE.md`, which holds the git push policy) load every session. **Re-read CLAUDE.md before every action.**
2. Read the memory index `~/.claude/projects/-home-coltontr419/memory/MEMORY.md` and these files in full:
   `bittensor-mining-lead.md`, `mvtrx-lessons.md`, `mvtrx-one-miner-plan.md`, and every `feedback-*.md`.
3. Read `~/futures-research/reports/decisions.md` from §1290 to the end (the last day of MVTRX work).
4. Re-create the 30-minute brief (CronCreate, minutes 13,43; session-only — see §6 for the brief text).
5. Run the status checks in §5 and tell the user what you see. Do NOT change any live miner until the user says so.

## 1. RULES (copy into CLAUDE.md; all are the user's standing instructions)

### Working style
- **Check every route before acting.** Don't stop at the first finding. List every candidate cause, measure each against the data
  (by book group, depth, size, spread, timing, inventory, per book, per window) before naming a cause or changing anything. The
  previous session repeatedly acted on its first explanation and had to retract it.
- **Record every problem and every solution permanently in memory, as it happens.** Append a line (problem → cause → fix/rule, with
  the decisions.md §) to `memory/mvtrx-lessons.md` in the same turn. Re-read the relevant lessons before similar actions.
- **Copy successful miners first.** Before any MVTRX strategy test, measure what the top UIDs actually do from their real trades/fills
  on our tape, and build the test from that. Takers' trades are visible; makers' resting orders are anonymous (only fills are visible).
  Trading behaviour may be copied from any good earner if our cap-safe pacing keeps it intact; **volume pacing and UID lifecycle only
  from long-lived UIDs (≥ 7 days, ideally 14+)** — never from churn-and-burn fleets. State the source UIDs' ages in every study.
- **Test length:** tests for LARGE improvements run **1 wall hour on ALL books** (no book splits — splitting into arms raised noise
  ≈ 1.7× and the user banned it). Only fine-tuning tests for small effects may run longer, and only when the 1-hour read can't separate
  the effect from noise (say so and why). Noise floor (measured 11-08 on x2): 1 wall hour ≈ 11.5 sim min ≈ 190 $300-book fills
  (±0.20 bp) and ≈ 95 calm fills (±0.30 bp); smallest trustworthy A-vs-B difference ≈ 0.6 bp ($300) / 0.85 bp (calm).
- **Lead every test read with the fill-level difference ± block-bootstrap noise** (`abtest.py`-style, or `vfill.py` for validator-style
  marks). Quote the validator's R/C quality ratio only when the captured base is large (a ratio on a captured base of ≈ 9 units was
  pure noise and was reported as a win — wrong).
- **When a miner is clearly and steadily above the median, say so plainly and stop changing it** (only safety fixes/rollbacks).
- **One miner per day plan:** if x2 and x4 are both pruned (likely tonight), register ONE miner per day and run constant tests on it
  until a strategy can survive for weeks. No scaling until then.
- **Scaling** only if the makers clearly clear the prune line (user's condition).
- Explain things in plain terms; keep briefs short. Real clock times only (`TZ=America/Chicago date`); the user is in Texas, **CT = UTC−6**.
  End every message involving runs/tests with an **ETA line in CT**.
- **30-minute briefs** for every run/test (recurring CronCreate at :13/:43, short brief, until the final reading is in). Crons are
  session-only and expire after 7 days — re-create after a restart. If a brief was missed because the session slept, say so and run it.
- Name miners by hotkey (x1, x2, x3, x4) — that's how they appear in the earnings report.
- Don't call the night/day "done" early; keep suggesting useful work. Don't pause on nulls.
- Use Claude-family models for nothing inside miners: **Harnyx and Hone agents must use OpenAI or open-weight models** (Hone's terms
  forbid Claude; the user prefers it for Harnyx too). Tagging subnets used OpenAI/open-weight.

### Safety / operations
- **Never print tokens or keys.** Secrets are saved by the user on the server via `read -s`; never ask for secrets in chat.
- **Coldkey stays on the laptop** (`~/.bittensor/wallets/main`). Only `coldkeypub.txt` and hotkey files go to servers.
- **The user runs btcli** for registration and unstaking, with VS Code closed (laptop btcli is OOM-killed while VS Code runs):
  `~/btcli/bin/btcli` (v9.23.2, not on PATH). You never run btcli and never use the coldkey password. Give the user exact commands.
  - Register: `~/btcli/bin/btcli subnet register --netuid 79 --wallet.name main --wallet.hotkey <hk>` (≈ 0.137 TAO on 11-08).
  - New hotkey: `~/btcli/bin/btcli wallet new_hotkey --wallet.name main --wallet.hotkey <hk>` (then copy ONLY the hotkey file + pub to the server).
  - Unstake: batch `--all-hotkeys --all` FAILS (MEV shield / block limits). Use per hotkey:
    `~/btcli/bin/btcli stake remove --wallet.name main --wallet.hotkey <hk> --all --no-mev-protection`.
- **Never grant the MVTRX exchange staking proxy.** The "AGENT NOT READY / proxy MISSING / cannot settle trades" banner at start is normal.
- **Kill exact PIDs only** — never `pkill` / `pgrep -f` loops with a pattern that can match your own command (this killed the session's
  own shell twice; most recently 11-08 2:15 PM). List with `ps -eo pid,args | grep ... | grep -v grep`, then kill the PID.
- **Our UIDs must never trade each other.** No wash trading, no feeding our makers with our takers (the validator's P11 "feeder ring"
  penalty defeats it anyway).
- **Fresh registration check (chain) minutes before any restart, read or "healthy" call.**
- Low-risk MVTRX parameter tests/restarts are pre-approved; **spending (registrations, boxes), keys/wallets, and changes to the
  futures droplet need the user's yes.**
- **Pacing must never let volume hit the validator's cap** (hard requirement).
- No changes to a frozen/above-median miner without approval; no live changes while the user is away except safety and rolling back
  a change that clearly hurts.
- Commits: `git -c user.name=DevColton -c user.email=noreply@example.invalid commit`, message ends with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; push after each commit; never force-push; never stage `.env` or `data/`.
  Log every decision/result as a new § in `reports/decisions.md` (next free number: **§1309**).
- Remote Python via ssh heredocs breaks on quotes — write a script file locally, `scp` it, run it.
- After every restart verify `ActiveEnterTimestamp` changed (a syntax error once silently skipped a restart).

## 2. Goal and context
- Overall goal: automated income, **$10k+/month** (raised 11-03; $2k was the floor). Bittensor is the current arena (crypto payouts OK).
- MVTRX (SN79) is the main subnet. Pay is split from a fixed pool; the field median UID ≈ $190–210/month; top operators run fleets.
- Long-lived benchmark fleet: **operator coldkey 5F1F2JMu** — 37–38 identical pure-maker UIDs, many 14–28 days old,
  ≈ $9,990/month total, median ≈ $263/UID, live combined ≈ 0.33–0.41, making credit ≈ 330–480. Our makers should match them.

## 3. Infrastructure
- **Laptop**: Chromebook Linux (`penguin`), repo `~/futures-research` (origin github.com/coltontr419-droid/futures-research, private).
  MVTRX code: `~/futures-research/deploy/sn79/` (QuoteAgent.py, test_pace.py, all analysis scripts). Other subnets: `deploy/sn5`,
  `sn33`, `sn50`, `sn61`, `sn67`, `sn83`, `sn92`, `sn101`, `subnet_scan.py`, `screen_weekly.sh`.
- **MVTRX lab box** `ssh mvtrx-lab` = 157.245.86.147 (DigitalOcean, 4 vCPU / 8 GB, ≈ $48/mo, key ~/.ssh/miner_box). `/opt/mvtrx`:
  agents/QuoteAgent.py (deployed agent; must equal the repo copy — compare md5), venv `/opt/mvtrx/venv`, validator repo
  `/opt/mvtrx/repo` (taos: debeta.py, reward.py, query.py, config), units `/etc/systemd/system/mvtrx-x{1,2,3,4}.service`.
  Each miner ≈ 170–190 MB RAM, ≈ 7% of one core; ≈ 15–20 more fit.
- **Futures droplet** `ssh futures-droplet` = 157.230.91.2 (shared with the user's REAL futures bot `futures-bot` — confirm before
  ANY change there). Bittensor parts: `/opt/tag101` (minerwatch.py, earnings_all.py → `/opt/tag101/earnings_all.csv` hourly,
  minerwatch-report (Discord, every 4 h at :05), minerwatch-health, labalerts.py (Discord #miners, every 5 min, reads the lab box's
  `/opt/mvtrx/alerts.txt` through a forced-command read-only key `/root/.ssh/lab_alerts`)). Miners are discovered from
  `/root/.bittensor/wallets/main/hotkeys/x*pub.txt` on the droplet — copy each new `<hk>pub.txt` there (x1–x4 already present).
- **Public validator dashboard** (Grafana, GET only): `https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query`
  with `miner_gauges{miner_gauge_name="debeta_skill|debeta_skill_books_kept|debeta_making|combined_score|score|dropped",agent_id="<uid>"}`
  and `agent_gauges{agent_gauge_name="daily_volume"}`. Use `curl` (Python requests got 403). It goes down at times (502 / blank) —
  miners are unaffected; use chain emission for prune checks. Gauge helper: `UIDQ=<uid> /opt/mvtrx/x1_gauge.sh`.
- **Chain**: `bt.Subtensor(network="finney")`, `metagraph(79, lite=True)`; archive node `bt.Subtensor(network="archive")` for history
  (BlockAtRegistration, Keys, Owner, Incentive at past blocks).

## 4. LIVE STATE at handoff (11-08 ≈ 3:15 PM CT)

| Miner | UID | Hotkey | Role | Protection ends | Pay (2 PM) | Setup |
|---|---|---|---|---|---|---|
| x2 | 212 | x2 (5H94z1K2) | maker, CONTROL | ≈ 6:40 PM CT 11-08 | $92.3/mo | all books except 4-dec, thin rule OFF everywhere, $300 ladder 2:5:10 |
| x4 | 58 | x4 (5E1bojcP) | maker, TEST + tape recorder | ≈ 7:05 PM CT 11-08 | $87.0/mo | combined test since 2:50 PM (see below) |

- **Prune risk (top priority):** 3:00 PM chain check — the lowest unprotected UIDs were $97, 99, 99, 101, 102, 108; x2 ≈ $92, x4 ≈ $88
  would be the lowest of all 195 unprotected. Pay flat/slightly down. **Both are likely to be pruned tonight.** If so → the one-miner-
  per-day plan (§1 rules). Pruned UIDs: stop + disable the service, remove the UID line from `/opt/mvtrx/our_uids.txt`, remove its
  `locks/maker_<uid>.hb`, and **if the tape recorder (x4) is pruned, the tape goes blind** (see §7).
- **x4 combined test since 2:50 PM CT (§1307, T ≈ sim s 25,117):** every book (no arms): calm-book ladder (touch + 1/2/4 ticks behind,
  $1.8k each: `mk_calm_lad=1:2:4 mk_calm_lad_size=0.036`) + $300 inside quoting when spread ≥ 5 ticks (`mk_vol_inside=5`) + thin rule on
  $300 books only (`mk_thin_ratio=0.77 mk_thin_vol_off=0 mk_thin_only_vol=1`) + 4-dec books skipped (`skip_file=books_skip_4dec.txt`).
  **1-hour read due ≈ 3:50 PM CT**: `ssh mvtrx-lab 'sh /opt/mvtrx/qread.sh 25117'` (validator totals per group; it asks for 3 arms, so ADD
  x4's arm rows) AND the fill-level A/B with noise: `python3 /opt/mvtrx/vfill.py live_tape_x3.jsonl 25117 <now sim s> x4=58 x2=212`
  (validator-style marks; compare only, absolute levels run high) — judge on noise widths (≥ 2 = real).
- **Next test built, ready (off by default):** trade-flow pull on $300 books — `mk_tflow_usd=1000 mk_tflow_win=10` (pull the bid while
  10-s taker flow buys > $1k, pull the ask while it sells). Basis: x2's worst $300 fills (44% of $, kept÷edge 0.25) came while trades
  hit the OTHER side (§1305).
- Pace (both): `pace_cap=450000 pace_steady=450000 pace_start=100000` + ledger `pace_UIDN.ledger` (§1299). Cap-tested worst 24 h $478.8k.
- `our_uids.txt`: `212 maker x2 11249` / `58 maker x4 11544` (4th field = start sim s, mandatory). No takers → self-trade impossible.
- Units ready, DISABLED: `mvtrx-x1` (port 8101) and `mvtrx-x3` (8103) = x2's setup with hotkey x1/x3 (those hotkeys are free —
  UIDs 194/201 were pruned). Launch any newly registered miner with **`sh /opt/mvtrx/launch_maker.sh <name>`** (checks registration,
  writes our_uids with the current sim s BEFORE start, moves an old ledger aside, removes a stale heartbeat, starts, verifies).
  Then copy `<name>pub.txt` to the droplet if missing.
- Timers on the lab box: `mvtrx-overnight.timer` (watchdog every 10 min: status per our_uids, registration check, self-trade guard
  — stops mvtrx-x1 on a real self-trade, pace_sync volume check, alerts) and `mvtrx-taperotate.timer` (rotates the tape > 2 GB in place).
  Disabled: mvtrx-autorefit (no taker), mvtrx-retrain. Logs: `/opt/mvtrx/overnight_log.txt`, alerts `/opt/mvtrx/alerts.txt`
  (lines MUST be `ALERT <epoch> text` — the Discord forwarder posts only lines newer than its last).
- Discord alerts removed by the user: "dropped N instructions", "NOT REGISTERED" (the droplet's push-out alert covers prunes),
  "volume check failed". Remaining: service down, errors, book within 10% of cap, no fills lately, self-trade, box unreachable, watchdog stopped.
- **Open items:** `tag101-m3.service` is still RUNNING on the futures droplet and the tag101-bench-read timer is active although Tag101
  was closed 11-03 — check whether its UID is still registered and ask the user whether to disable it. Synth forward-test timer
  (`synth-forward`, lab box) still runs; synth-s1 miner staged/disabled.

## 5. Status checks
```
TZ=America/Chicago date
ssh mvtrx-lab 'tail -14 /opt/mvtrx/overnight_log.txt | cut -c1-135; grep "^ALERT [0-9]" /opt/mvtrx/alerts.txt | tail -3; python3 /opt/mvtrx/selftrade.py; systemctl is-active mvtrx-x2 mvtrx-x4; for u in 212 58 216 87; do UIDQ=$u /opt/mvtrx/x1_gauge.sh; done'
ssh futures-droplet 'grep ",MVTRX," /opt/tag101/earnings_all.csv | tail -3'
```
Prune-rank check (chain):
```
ssh mvtrx-lab 'cd /tmp && timeout 250 /opt/mvtrx/venv/bin/python -c "import bittensor as bt, numpy as np; st=bt.Subtensor(network=\"finney\"); m=st.metagraph(79, lite=True); blk=st.get_current_block(); imm=st.query_subtensor(\"ImmunityPeriod\",params=[79]).value; E=np.array(m.emission,dtype=float); rb=np.array([int(st.query_subtensor(\"BlockAtRegistration\",params=[79,u]).value) for u in range(256)]); non=sorted([u for u in range(1,256) if blk-rb[u]>=imm], key=lambda u:E[u]); print([round(E[u]/E[212],2) for u in non[:8]], \"x4/x2\", round(E[58]/E[212],2))"'
```
(ratios vs x2's emission; x2's $ comes from the earnings log). Registration check: compare `m.hotkeys[uid]` with
`json.load(open('/root/.bittensor/wallets/main/hotkeys/<hk>'))['ss58Address']`.

## 6. 30-minute brief text (re-create with CronCreate "13,43 * * * *")
Include: rules reminder (real CT times, registration check before restarts, plain terms, short), live state (§4), the pending read
command(s) and judging rule (fill-level difference ± noise; ≥ 2 noise widths), prune risk + rank check, the one-miner plan, status
commands (§5), commit identity, ETA line. Update it every time the setup changes.

## 7. MVTRX (SN79) — how the subnet works (verified from validator code; don't re-derive)
- **Sim clock:** ≈ 11.5–12 sim minutes per wall hour → **24 sim hours ≈ 5 wall days**. Sim-day reset sends the clock 86,400 → 0
  (stored timestamps then sit in the future: `_clock_check` in QuoteAgent shifts them; copy-hold legs too).
- **Books:** 128. ids 0–62 = "$300" books (≈ $300 price, 2-decimal, tick $0.01 ≈ 0.33 bp, spread ≈ 2 bp); 63–101 = calm ≈ $30 books
  (tick $0.01 ≈ 3.3 bp, spread ≈ 6.8 bp); 102–127 = 4-decimal books.
- **Volume cap:** 10 × wealth (≈ $500k) per book per 24 sim h, maker + taker volume; past it the validator DROPS placements (no score
  penalty). Cleared only by deregistration. Our pace bucket keeps every book ≤ $450k (backstop) — never hit the cap.
- **max_instructions_per_book = 5 per reply**; the excess is DROPPED. Budget instructions per book; pull many orders with ONE
  `cancel_orders` (the batched-cancel fix, §1293).
- **Delay:** the validator turns round-trip time into an order delay; speed (≈ 2 ms) is not our problem. Validator in Chicago, 19 ms RTT.
- **Making credit** (making pool ≈ half of emission): Σ_book 2·min(buy,sell) of captured spread × quality. Captured AND realized are
  measured vs a **print-centred mid** (size-weighted, 15 prints each side; background-sided prints for the realized mark at the first
  print ≥ 20 sim s later). **Quality = clamp(R/C, 0, 1) is ONE number per miner** over all books → a low-quality book group drags every
  book's credit (§1302). `making_exact.py` runs the validator's own code (`cd /opt/mvtrx/repo; /opt/mvtrx/venv/bin/python
  /opt/mvtrx/making_exact.py <tape> <uid> <arms> --since <sim min>`) — the truth, but totals only (no noise width).
- **Skill:** per book alpha = Σ inventory × Δmid − mean inventory × drift (fill price never charged), counted only if |α| ≥ 2.3 bp of
  notional; kappa across kept books; plain 3-sim-h window by default; coverage factor min(1, books/80). Our makers' skill ≈ 0; the fleet's
  is negative (−0.2…−0.6) — the fleet earns from making.
- **Paid score:** age-annealed EMA: a young UID's paid score ≈ the plain mean of all its rounds (weight max(time decay, 1/(k+1))) →
  pay lags the live score by many hours; hourly pay snapshots are noisy. The validator wipes a slot's history on deregistration.
- **Pruning:** each registration (≈ 2–3/hour) removes the lowest-emission UID whose 24 h protection (7200 blocks) has ended. The line
  moves (≈ $52 → $89 → $97–99 on 11-07/08). New UIDs need ≈ the line within 24 h.
- **Overlap:** identical makers on the same books share/kill the SKILL part, not making credit (§1289). Splitting books between makers
  cut making credit and was undone (§1290). The fleet runs 37 makers on the same books at ≈ 0.4 live.
- **Pacing:** token bucket per book (rate = pace_steady/86400 per sim s, burst 900 s, can go negative; quote/open only when positive;
  exits always go); ledger `pace_<uid>.ledger` is the record; `pace_sync.py` charges any gap vs the validator's daily_volume. On a
  restart the ledger is replayed through the bucket from each book's first fill — so **never remove pace_start on a running UID** (it
  would block it for hours). Front-loaded budget (pace_steady 350k) cut volume ≈ 25% below the fleet → now steady 450k (§1299).
  Our makers are PACE-BOUND (≈ 100–110 of 128 books paced at any moment) — making credit tracks the steady pace.
- Field facts: the field median maker earns ≈ $200; settled UIDs: live 0.40–0.45 ≈ $250–275/mo, 0.53 ≈ $390. Churn fleets
  (5G3oVFjL, 5G9URk3b, 5DkwcgDZ) spend volume fast and rotate UIDs; long-lived 5F1F2JMu is the model. Registration ≈ 0.12–0.14 TAO.

## 8. MVTRX — where we are on quality (the real gap; §1301–§1308)
Validator-exact, x2 vs fleet UID 216 since 6:17 AM 11-08:
- **$300 books:** quality x2 0.26 vs fleet 0.65 (similar captured spread). Fleet keeps more in EVERY bucket (size, depth, spread,
  inventory, incoming trade size); fleet better on 57/60 of the same books; not a fundamental lean; fleet is only 7% of $300 maker
  volume (no "liquidity wall"). → It's the fleet's BEHAVIOUR/PRESENCE: per UID about half our $300 fill rate with ≈ 3× kept per fill;
  likely pull rules. x2's bad buckets: thin own queue (35% of $, kept÷edge 0.28) and trades hitting the other side (44%, 0.25).
  Thin rule on $300 tested 1:50–2:50 PM: **no effect** (+0.07 ± 0.24 bp). Trade-flow pull = next candidate (built).
- **Calm books:** fleet edge +7.5 bp vs ours +3.3; fleet 38% of calm $ at the touch, 46% 1–2 ticks behind (edge +8.7), 14% 3+ behind
  (+13.2) → touch order PLUS a resting ladder behind it (being tested on x4 now). Moving the touch order back alone lost (§1300).
  Sticky (keep queue place) looked mildly positive but within noise.
- **4-decimal books:** quality ≈ 0 → skipped on both makers (+13% predicted).
- Ruled out / don't re-test: skipping "worst" books (they change every hour), bigger orders alone ($3.6k), trend pull (−18% credit),
  lazy fleet-pattern $3.6k deep orders (cut skill), calm-distance alone, thin rule off on $300 (quality 0.26), quote model guard
  (halves credit), smaller maker orders, front-loaded 350k pace.

## 9. MVTRX — taker (skill) history (all closed for now)
- Fitted reversal predictor (rev_model v1/v3/v4) worked briefly (+3.5 bp at 600 s) but decays within ≈ a day; refits needed; v5 refit
  candidate failed the gate. Profit-target exits lost to the clock; add-to-losers/winners lost; copy of top takers (bursts, 10% slices
  at +6 bp, no stop) lost (§1283: x1 had no edge); delayed copies of the best takers (UIDs 44/247) fail under our pace (kappa collapses);
  10-minute exit lost (§1289). Long-lived pure takers (94, 186) were weak live. No taker runs now; autorefit disabled.

## 10. MVTRX — every problem hit and its fix (also in memory/mvtrx-lessons.md)
- Pattern kills killed our own shell → exact PIDs only.
- Restarting on a stale registration read → fresh chain check first.
- New UID with our_uids start 0 → self-trade guard counted the slot's previous owner and stopped x1 → launch_maker.sh writes the start first.
- Stale `maker_<uid>.hb` after a reset froze x1 → heartbeat alive check (age + file mtime) and launcher deletes stale ones.
- Only tape recorder pruned → tape + self-trade guard blind 4.5 h → move `tape=` to another live maker immediately (same file
  `/opt/mvtrx/live_tape_x3.jsonl`; scripts expect that path).
- Converting an unprotected slot (x1 taker → maker) → pruned in 38 min → new makers need a fresh registration.
- Sim-day reset froze the clock-based logic → `_clock_check`.
- Scripts measured "last N sim min" from the tape's max ts, which was PRE-RESET data (scored a slot's previous owner) → every tape
  script filters `ts < 60000 s` (current sim) — re-check after the next sim reset.
- Session crons stop when the laptop closes → server-side systemd timers for anything needed while away.
- Discord re-posted stale lines → `ALERT <epoch>` format + forwarder posts only newer than its last.
- ssh heredoc quoting broke patches → scp a script file.
- A wait command's syntax error silently skipped a restart → verify ActiveEnterTimestamp.
- Dashboard API down → not a miner problem; don't alert on it.
- Autorefit kept targeting a removed taker → disable timers tied to removed roles.
- >5 instructions per book dropped (ladder cancels) → batched cancel_orders (§1293).
- Ladder level-coverage tolerance ±1 tick made adjacent levels never place → tolerance = half the smallest level gap (§1303).
- Front-loaded pace cut volume → steady 450k (§1299).
- Overstated test results from too-short windows / tiny captured bases → fill-level ± noise, 1-hour all-books tests.
- Earlier (10-31…11-07): quadratic CSV trim stalled restarts (fix_trim.sh); model30_of quote model was in dollars (pull fired 100% on
  4-dec) → makers run alpha_k 0, pull 0; x3 ran 5× over pace until the ledger exposed it → pace from minute one; volume-cap silent
  drops diagnosed with dbg=1; validator inventory = fills inside its window (held positions invisible to skill).

## 11. MVTRX key files (lab box /opt/mvtrx unless noted; repo copies in deploy/sn79)
QuoteAgent.py (all settings documented inline with §); test_pace.py (cap/pace/ladder/copy/calm/inside/trade-flow tests — run before
every deploy: `/opt/mvtrx/venv/bin/python test_pace.py agents/<file>`, must print ALL PASS); launch_maker.sh; overnight.sh (watchdog);
pace_sync.py; selftrade.py/.sh; making_exact.py; qread.sh; vfill.py (validator-style per-fill A/B); fillrate.py; fillprobe.py;
stateprobe.py; takersize.py; fundprobe.py; qualgap.py; m300copy.py; spreadpick.py; fleetx.py; earners.py; skill_val.py (current-sim
fixed); mirror_val.py; holdval.py; tape_rotate.sh; x1_gauge.sh; mktest_read.sh; books_skip_4dec.txt; books_none.txt;
books_skip_mod3_*.txt; our_uids.txt; locks/; pace_<uid>.ledger. Unit backups `/opt/mvtrx/mvtrx-*.service.pre-*`.
Deploy pattern: edit deploy/sn79/QuoteAgent.py → py_compile → scp to `/opt/mvtrx/agents/QuoteAgent.<tag>.py` → run test_pace on it →
backup + copy over agents/QuoteAgent.py → registration check → edit unit (backup) → daemon-reload → restart → verify → log § → commit.

## 12. Other subnets (closed/parked — don't redo the screens)
- **SN101 Tag101** — CLOSED 11-03: pay = consensus with one ~117-UID operator's tags; all 7 tag-style families lost (−0.17…−1.04/round).
  Validator history keyed by UID and NOT reset on re-registration. (m3 service still running — open item.)
- **SN33 ReadyAI** — closed: validators locked to gpt-5.2; weights rank-based; big operators re-register every ≈ 24 min; our fixes only
  passed newcomers; recommended not to re-register.
- **SN50 Synth** — forward test running (lab box /opt/synth, daily 06:30 UTC); Crypto-1h ≈ 1.3× median in backtests; register only after
  ≥ 5 forward days with Crypto-1h + one more competition ≥ median; miner staged (synth-s1, disabled; needs ≈ 0.8 TAO).
- **SN5 Hone** — ≈ $1,050/UID/month flat; GLM-5.2 6/10 SWE-bench at $0.25/task; ≈ $15k/month to answer all tasks → needs ~15+ UIDs;
  no Claude (terms). Waiting for subnet income to live-test 2–3 UIDs. Keys /opt/hone/*.env.
- **SN67 Harnyx** — research agent; champion code public; main tier ≈ $590/month vs ≈ $560 costs at $0.155/task → only worth it ~3×
  cheaper, with novelty, or by taking the title. No Claude in the agent. Repo /opt/harnyx.
- **SN82 Noah** — parked (capital-for-yield loop on its own token; 8.4 TAO burn).
- **SN92 REAX** — watch (GPU inference, ≈ $1.1–1.8k/hotkey margin, token risk); user's call.
- **SN61 RedTeam** — parked (only BEX Tracer (skipped) + ADA (needs paid anti-detect browsers)).
- **CliqueAI** — closed (enumeration infeasible). **MANTIS** — skip (median too small).
- Only ~12 subnets pay the median miner > $100; all studied (§1212). Weekly screen script: deploy/screen_weekly.sh.

## 13. Money
- Stake on our hotkeys is tiny (≈ 0.0235 TAO at 11-07 evening). Registration ≈ 0.137 TAO. The user tops up TAO for registrations;
  always state the cost and get a yes.

## 14. What to do next (in order)
1. ≈ 3:50 PM CT: read x4's combined test (both measures, noise widths). Keep what clearly wins; roll back what clearly loses; propose
   applying winners to x2 (user decides).
2. Then put the trade-flow pull on x4 for a 1-hour all-books test (keep whatever won).
3. ≈ 5 PM CT: prune-rank check; report plainly.
4. If pruned: clean up (§4), move the tape if x4 goes, then the one-miner-per-day plan with the best-known setup via launch_maker.sh
   after the user registers (and copies `<hk>pub.txt` to the droplet if new).
5. Keep studying the fleet's $300 presence pattern (pull rules) and calm ladder results; every finding → mvtrx-lessons.md + decisions.md.
