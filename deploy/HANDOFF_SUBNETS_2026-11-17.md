# Handoff — Bittensor subnets other than MVTRX (SN79), 2026-11-17

You are picking up the **non-MVTRX subnet research**. MVTRX has its own session and handoff
(`deploy/sn79/HANDOFF_2026-11-15.md`). **Do not touch the MVTRX miners, the lab box's mvtrx-* services, or the futures droplet's bot.**
The user's goal: be ready to enter other subnets once MVTRX income arrives, toward $10k+/month in total.

Before doing anything, read `deploy/sn79/CLAUDE.md` §1 (rules) and the memory index
`~/.claude/projects/-home-coltontr419/memory/MEMORY.md`, especially `subnet-redive-2026-11-17.md`, `hone-sn5-lead.md`,
`harnyx-sn67-lead.md`, `noah-sn82-parked.md` and `bittensor-mining-lead.md`. All detail lives in `reports/decisions.md`
(the § numbers below); when this file and a newer § disagree, the newer § wins.

---

## 1. Rules that apply to subnet work

- **Spending, registrations, keys and new servers need the user's yes.** The user runs btcli themself, from the laptop with VS Code closed:
  `~/btcli/bin/btcli subnet register --netuid <N> --wallet.name main --wallet.hotkey <hk>`. Never run btcli and never handle the coldkey password.
  The coldkey stays on the laptop; only `coldkeypub.txt` and hotkey files go to servers.
  Unstake per hotkey: `btcli stake remove --wallet.name main --wallet.hotkey <hk> --all --no-mev-protection`, because the batch unstake fails.
- **Never print tokens or keys.** The user saves secrets on the server with `read -s`; never ask for them in chat.
- **Futures droplet** (`ssh futures-droplet`) runs the real futures bot: confirm with the user before any change there.
- **Lab box** (`ssh mvtrx-lab`, 157.245.86.147, 4 vCPU / 8 GB) belongs to MVTRX. Read-only chain scripts are OK with
  `nice -n 19 /opt/mvtrx/venv/bin/python`. No heavy CPU jobs there while MVTRX tests run (e.g. a Minos GATK backtest needs its own box).
- Remote Python: write the script locally, `scp` it, then run it. ssh heredocs with quotes break.
- **Kill exact PIDs only**; never use pattern kills.
- **No Claude models inside miners.** Hone's terms forbid it, and the user wants the same for Harnyx and tagging work. Use OpenAI or open-weight models.
- **Arena rules from the user:**
  - no prediction-market trading and no liquidity/maker reward programs;
  - crypto payouts are fine;
  - start small, then scale what earns live;
  - no part-year/seasonal strategies;
  - no detection-evasion or user-tracking work (RedTeam BEX Tracer / Humanize Behaviour were skipped for this);
  - no sybil-style "outvote the consensus with many UIDs".
- Check every route before concluding. Record every lesson in memory, and log decisions as a new § in `reports/decisions.md`.
- Commits: `git -c user.name=DevColton -c user.email=noreply@example.invalid commit`, then push. Never force-push. Never stage `.env` or `data/`.
- Plain language, real CT times (UTC−6), and an ETA line in CT on any message about runs.

## 2. General lessons (all subnets)

- **Pay math:** $/month per UID = `E[uid]` (alpha per tempo) × 7200/(tempo+1) × 30 × alpha price (TAO) × TAO $.
  This is `/opt/mvtrx/subnet_scan.py`. **Check pool depth** (`st.subnet(n).tao_in`) before believing it. For example, Noah's $8k/UID
  sits on a 2.1k-TAO pool against $205k/month of emission, so it can't be sold without crashing the price.
- **Prune line** = the lowest-paid non-immune UID. A new UID must beat it before immunity ends, or the next registration replaces it.
  If a subnet has fewer than 256 UIDs, nobody is pruned.
- **Validator history can be keyed by UID, not hotkey.** On Tag101 a new hotkey inherited the pruned owner's last 24 h (§1190). On MVTRX a
  slot can keep its inherited standing (§1241). One hour after registering, check that the score reset and is climbing.
- **Newcomers bias the rankings:** fresh, still-immune UIDs sit at the bottom, so "beating 20 UIDs" may only mean beating newcomers (§1211).
- **Offline/lab results often fail live.** Judge by live single-change runs against the field in the same window. Copy what paid UIDs
  actually do, and take pacing/lifecycle only from long-lived UIDs (≥ 7–14 days).
- **Flat-pay subnets** (Hone, ItsAI, Data Universe) pay everyone about the same: the cost of serving every task decides profit.
  **Winner-take-most subnets** (Minos, Ridges, SayGM, lium) have a median of $0; look at p90 and at the rank structure.
- Get identities on chain with `st.subnet(n).subnet_identity` (github_repo, subnet_url).
- **Weekly screen:** `deploy/screen_weekly.sh` runs on the lab box Mondays at 14:00 UTC. Outputs are `/opt/mvtrx/screens/scan_<date>.json`
  (keys: med, p75, p90, line, burn, topck, nck, paid, miners) and `changes.txt` (NEW PASS / MOVED). It also logs RedTeam's active challenges.

## 3. NEW STUDY 2026-11-17 — ranked readiness list (TAO $193)

Chain read (top earners, pot, ages) via `/tmp/claude-1000/sn/top.py`, and pool depth via `pool.py` (copies under `/tmp/top_ro.py` and `/tmp/pool_ro.py` on the lab box).

| Subnet | Miner pot $/mo | Who's paid | Burn | Pool TAO | Verdict |
|---|---|---|---|---|---|
| **SN107 Minos** | 479k | 28 UIDs avg ≥ $1.7k; 15 avg $11–75k | 0.99 | 20,172 | **#1 lead: offline backtest first** |
| SN50 Synth | 47k | top UID $1.1k; 27 > $500 | 0.80 | 9,667 | forward test passes the bar; verify $ |
| SN5 Hone | 207k | 216/245 > $500 (median $775) | 0.345 | 33,310 | ready plan: 2–3 UIDs once income |
| SN67 Harnyx | 41k | 2 champions $5k; ~many at $713 | 0.05 | 2,299 | break-even unless cheaper/novel |
| SN83 CliqueAI | 112k | 96 > $500, long-lived fleets | 0.10 | 7,727 | closed §1213 (diversity) |
| SN92 REAX | 134k | 65 > $500 (GPU) | 0.60 | 4,179 | watch; GPU rental + token risk |
| SN28 SayGM | 453k | one coldkey ≈ $250k | 0.20 | 28,116 | read emission rule before verdict |
| SN62 Ridges | 102k | 23 > $500, top $18k | 0.001 | 25,178 | must beat leader's SWE agent: hard |
| SN51 lium.io | 636k | 42 > $500 | 0.5 | 185,205 | needs a GPU fleet (capital) |
| SN82 Noah | 205k | 35 × ~$8k | 3.40 | 2,119 | parked: pool can't absorb sells |
| SN41 Almanac | 118k | 54 > $500 | 0.10 | 17,340 | excluded (prediction-market trading) |
| SN61 RedTeam | 38k | 37 > $500 (~$570 cap) | — | — | parked (§1219) |
| SN15 ORO / SN32 ItsAI / SN22 Desearch / SN13 Data Universe | 14k / 40k / 32k / 19k | ≤ $260 each | — | — | too small |

### 3a. SN107 Minos — details (the main new finding)

- **Repo:** minos-protocol/minos_subnet. Site: theminos.ai. Public API: `https://api.theminos.ai`.
- **The task:** every 72 min a round opens on a slice of a human chromosome. The live weights favour chr10 (36%), chr11 (24%), chr12 (11%) and chr13 (9%).
  The miner runs a variant caller on the round's BAM and submits a **config**: `gatk`, `deepvariant` or `bcftools` (freebayes was banned 2026-05-09).
  Validators (6–7) re-score with hap.py.
- **Scoring version v2:** `100 × (0.70 × core + 0.30 × germline)`, difficulty-weighted and gated. It also has an overcall guardrail of up to −45 points.
  See `docs/scoring.md` and `docs/tuning_guide.md`. Exposed GATK knobs include `standard_min_confidence_threshold_for_calling`,
  `min_base_quality_score` and `pcr_indel_model` (NONE for PCR-free GIAB). Full ranges: `/scoring/parameter-ranges` and `docs/parameter_ranges.md`.
- **Pay (live `/scoring/network-config`, 11-17):** `winner_weight 0.8`; ranks 2–20 share 0.2 with `dust_decay 0.9`
  (rank 2 ≈ 2.3% of the pot, rank 20 ≈ 0.35%); `burn_rate 0`.
  - Eligibility needs valid scores in **5 of the last 20 rounds**, so about 6 h of uptime before any pay.
  - `config_commitment_required: true`: configs are hash-committed, so you can't copy another miner's config mid-round.
  - Equal scores break ties by earliest submission or deterministic round data.
- **What 37 revealed rounds (11-15 → 11-17) show:**
  - About 55 submitters per round; **100% of the top 20 used GATK**.
  - The #1–#20 score gap has a median of **0.001**. The winner rotates: 37 rounds had ~15 different winners.
  - Average weight × pot: uid6 $75k, uid18 $57k, uid71 $55k, uid73/93/26 ≈ $35k, uid36/61 ≈ $25k, seven more at $11–15k; ranks 16–28 ≈ $1.7–3.9k/month.
  - The miner pot is ≈ $479k/month. Check: uid6's on-chain incentive of 0.79 equals ≈ $379k at that instant.
- **Unknowns and risks:**
  - Some eligible top-20 rows get weight 0. The code says "excluded rows deliberately receive no detailed public reason", so it is maybe an anti-sybil or duplicate-config rule.
  - The rules change often (winner weight 0.9 → 0.8; v1 → v2).
  - The sample is only 2 days.
  - It is unknown how fast GATK runs per round on 4 cores.
- **How to enter (research, then the user's yes):**
  1. **Offline backtest, no spending.** Past rounds release the BAM, truth and file hashes (`GET /verification/round/{id}`, `check_round.sh --download DIR`).
     Run GATK with several configs on a CPU box (not the MVTRX lab box during tests), score with hap.py (the repo's `--demo` mode prints the
     validator's score), and compare against each round's leaderboard (`/scoring/rounds/{id}/leaderboard`, revealed about 2 rounds later).
  2. If a config would land in the top 20 in most rounds, register 1 UID (0.99 TAO ≈ $190) on a box with ≥ 4 cores, 16 GB RAM, 60 GB disk and Docker
     (Bittensor 10.3.1), run 6 h to become eligible, then read the weight per round.
- **Useful endpoints:**
  - `/scoring/rounds?limit=40` (status, region, submission_count, identity_revealed);
  - `/scoring/rounds/{id}/leaderboard` (uid, hotkey, current_score, snp_final, indel_final, tool_name, weight, eligible, participation_count, submitted_at);
  - `/scoring/network-config`; `/health`.
  - Local copies are in `/tmp/claude-1000/sn/minos_*` (scratch; may be gone).

### 3b. Synth forward test (lab box `/opt/synth`, read-only check 11-17)

`/opt/synth/data/synth/forward/rollup.txt` covers 11-04 → 11-16, 13 forward days; the 11-03 backfill is in-sample.
- **crypto-24h:** best variant `todg_12_144_c_ou20@1.0`, rank 2/257, share 24.7%, modelled ≈ $4.4k/month. Other variants are $1.2–3.7k.
- **crypto-1h:** `tod1_30_60_vv25` is ≈ 2× the median UID (0.88% vs 0.43%), ≈ $155/month.
- **com/equ-24h:** rank ~245/257, ≈ $0.

**RESOLVED 11-17 (§1565): the rollup's $ model is an artefact** — field scores are keyed by UID (re-used slots carry the previous owner's scores), and the backtest skips the validator's worst-score backfill for new miners and the per-asset coefficients; its own method predicts a 0%-paid 5-day-old UID would take ≈ 89% of crypto-24h. Real 24h pay is flat (top 0.66% of emission ≈ $400/mo). Realistic Synth ≈ $150–600/UID after ≈ 10 days. **Original caveat:** the chain's best Synth UID earns only $1.1k/month in total, so the rollup's $ model overstates. Find out why before registering
(the per-competition pot split, or the share being computed against our own model set). The §1218 bar (≥ 5 forward days with Crypto-1h +
one more competition ≥ median) is met. The miner is staged: `synth-s1.service` and `synth-warm.timer` are DISABLED, hotkey s1, port 8103,
18/18 prompt types pass (§1221). Going live needs hotkey s1 + 0.8 TAO + the user's yes.

### 3c. Other re-checks 11-17

- **Hone:** 216/245 UIDs > $500, top $1.47k, median down $1,050 → $775. The plan is unchanged (memory `hone-sn5-lead.md`).
- **Harnyx:** many main-tier UIDs at **$713** (was $590); two champions at $5.4k / $4.7k. The pool is small (2.3k TAO).
- **SayGM (taostat/gm-miner, saygm.com):**
  - How it works: you resell upstream LLM API capacity from a Phala Cloud TEE (paid account, `gmcli`). Payout = the buyer's retail price − your declared discount;
    the spread = payout − upstream cost.
  - Concentration: one coldkey (5F1jj…) holds UIDs 72/126/89/122/148, about $250k/month.
  - Reselling Anthropic/OpenAI keys has a negative spread and a terms risk (the miner carries it per gm's terms). The only plausible edge is cheap
    open-weight hosts (DeepInfra / Chutes / Z.ai GLM).
  - **The emission scoring rule is still unread** (`docs/` has miner-terms, sourcing, multi-key-slots, reproducibility). Read it next.
- **Ridges (ridgesai/ridges, `utils/incentives.py`):** a new agent must beat the current leader by a threshold on performance or cost.
  The reward grows with the time since the last improvement and then decays (half-life). It is winner-take-most against strong SWE agents.
- **Almanac:** 95% of pay is market trading on beta.almanac.market with your own capital (`market_weight_share 0.95`); forecasting agents get 5%. Excluded.
- **lium.io:** GPU rental; the top UIDs make $20–105k but need H100 fleets.
- **Noah:** 38 miners at ~$8k, but the pool is 2.1k TAO, so it's unsellable at scale. Still capital-for-yield (§1224).

## 4. Earlier subnet history (what's been tried; don't redo)

- **SN101 Tag101 (tag X posts)** §1171–§1208, §1309:
  - Pay = 24 h mean score → softmax β 10. History is keyed by UID. The crowd fits "verbatim key phrases, gpt-4o-mini".
  - Our UIDs were pruned twice. **CLOSED.**
  - `tag101-m3` was found still running 11-08 and **disabled (§1309); verified inactive/disabled 11-17.** Note: the 11-17 report wrongly said it was still running.
  - `tag101-earnings.timer` is KEPT (it writes MVTRX earnings rows).
- **SN33 ReadyAI (conversation tagging)** §1173, §1184–§1201, §1210–§1211:
  - Validators grade with gpt-5.2: cosine to their own tags, weights cubed, a 25% owner burn.
  - 28% of our answers exceeded the 12 s timeout (fixed). Even with lab-verified fixes, UIDs settled ≈ $135 vs a ≈ $170 line. **CLOSED.**
- **SN83 CliqueAI (max clique)** §1165, §1172, §1195, §1213: our solver ties the best size on 93/98 problems, but pay rewards answer diversity
  and full enumeration is infeasible. **CLOSED.** (It now pays a $407 median, all to long-lived fleets.)
- **SN50 Synth (price-path forecasts)** §1164–§1170, §1205, §1214–§1218, §1221–§1222, §1229:
  - Crypto-1h above the median on all 5 assets; crypto-24h wins in calm markets and loses on volatile days. That loss is not a width error; DVOL widening made it worse.
  - Com/Equ is history-limited.
  - The forward test runs daily (timer `synth-forward`, 06:30 UTC).
- **SN5 Hone (coding agents)** §1180, §1198, §1225–§1227:
  - Pay ∝ pass rate. Farms submit one answer from many UIDs (byte-identical answers are graded once), so pay is flat.
  - GLM-5.2 solved 6/10 SWE-bench in Hone's limit at $0.25/task; DeepSeek V4 Pro managed 2/10 on Terminal-Bench.
  - Answering all ~2,000 tasks/day ≈ $15k/month, so it needs ~15+ UIDs or a cheaper model.
  - Keys: `/opt/hone/openrouter.env` (hit its $20 limit) and `cerebras.env`. Scripts are in `deploy/sn5/`, `/opt/hone`, `/opt/swe`.
- **SN67 Harnyx (research agent)** §1231: a daily 30-task batch (10 qualifying + 20 main).
  - Main entry: beat the champion by 10 points, or match it ≥ 10% cheaper or faster.
  - The champion's code is public (MCP `get_miner_script`). Each validator runs the agent separately, so cost is ×4. The local-eval tool exists.
  - Repo at `/opt/harnyx` on the lab box; `deploy/sn67/`.
- **SN92 REAX (verified inference)** §1220: full GPU stacks earned ≈ $2.6k/UID, but the inference pool halved as emissions moved to
  model-training winners, and the token fell 35%. WATCH; pilot only after 2 weeks of a stable inference pool.
- **SN61 RedTeam** §1203, §1219: only BEX Tracer (skipped) and ADA (needs paid anti-detect browsers, 0.9 bar) are active. PARKED; the weekly screen watches for FlowRadar.
- **SN82 Noah** §1224: pays √(permanent NOAH contributions); a capital-for-yield loop. PARKED.
- **SN123 MANTIS:** skipped (median too small; contribution-based, so duplicate UIDs add nothing).
- **SN22 Desearch:** poor fit (≈ 50% of the score needs the paid X API).
- **SN32 ItsAI:** §1198 said it paid nothing; it now shows a $165 median, flat. Small.

## 5. Suggested order when money comes in

1. **Minos offline backtest** (cheap CPU box, about $20–50 for a few days, user's yes): if it reaches the top 20 → 1 UID (~$190).
2. **Synth:** resolve the $-model vs chain gap. If it's real → register s1 (0.8 TAO).
3. **Hone:** 2–3 UIDs with GLM-5.2 / DeepSeek via OpenRouter (prompt caching and step limits first).
4. Read SayGM's emission rule; re-check REAX's inference pool and Harnyx's tier economics.
