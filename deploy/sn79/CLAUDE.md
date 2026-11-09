# SN79 / Bittensor mining — CLAUDE.md

Re-read this file before every action.

## 1. RULES (copy into CLAUDE.md; all are the user's standing instructions)

### Working style
- **Check every route before acting.** Don't stop at the first finding. List every candidate cause, measure each against the data
  (by book group, depth, size, spread, timing, inventory, per book, per window) before naming a cause or changing anything. The
  previous session repeatedly acted on its first explanation and had to retract it.
- **Keep searching until there is nothing else to find** (user 11-08 6:10 PM): when researching issues/improvements, don't stop at the first
  problem found — it could cover up a bigger one that would help more. List what's left to check after every finding and keep going until every
  route is measured; report the full list, ranked by size.
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
  Log every decision/result as a new § in `reports/decisions.md` (next free number: **§1310**; check the last § in the file).
- Remote Python via ssh heredocs breaks on quotes — write a script file locally, `scp` it, run it.
- After every restart verify `ActiveEnterTimestamp` changed (a syntax error once silently skipped a restart).

## Current state / where to look
- Full handoff (live state, infrastructure, status checks, subnet mechanics, next steps): `HANDOFF_BITTENSOR_2026-11-08.md` (this folder).
  When it and `~/futures-research/reports/decisions.md` disagree, the newer decisions.md § wins.
- Memory: `~/.claude/projects/-home-coltontr419/memory/MEMORY.md` → `bittensor-mining-lead.md`, `mvtrx-lessons.md`
  (append every problem/fix), `mvtrx-one-miner-plan.md`, and every `feedback-*.md`.
- Repo-wide rules (git push policy): `~/futures-research/CLAUDE.md`.
