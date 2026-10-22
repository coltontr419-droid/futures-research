# Online profit — everything surveyed (2026-10-22)

Criteria used throughout: legitimate counterparty, starts at ~$100-200, can scale past $2,000/month, and how much is time vs. a repeatable edge.
Figures are realistic ranges from the sources cited in decisions.md and the web research of 2026-10-22 (many sources are vendor blogs — treat as
directional). "Tested" = measured by this programme; "desk" = research only.

## A. Markets and trading (tested)
| Arena | Result | Fits? |
|---|---|---|
| Tradeify futures props (deployed plan) | Only structural earner found: positive even at zero edge (≈ +$4-6k per 4-month run in backtests) | **Yes — live soon** |
| Other futures props (LucidPro, TradeDay, TPT, Phidias, Topstep, Alpha, MFF, Bulenox, FFF, Top One) | All negative once consistency rules are modelled (§766, §770); FundedNext Futures unmodelled | No (re-check FundedNext after Tradeify payouts) |
| Forex / CFD / crypto / stock props | Excluded by the user; options props don't exist | — |
| US stock anomalies (SSR, gaps, LULD, new listings, index deletions) | None survive costs (§854-866) | No |
| Crypto cross-exchange, listings, delistings, stablecoins | Dust to ~$300-500/month (§841-859, §870) | No |
| Prediction markets: mispricing / cross-venue / lag | ~30 families closed, no edge | No |
| Prediction-market liquidity rewards (Kalshi, Polymarket US, Gemini) | Kalshi thin-side: net loss; event-settled series small; Polymarket $80 test live; Gemini G1 shadow running | Pending (user: no new ones) |
| DFS overlays (DraftKings) | ~$24 a slate for one account; user lost money before | No |
| Sports betting / horse racing | Illegal in Texas (except prediction markets) | — |

## B. Structural corporate events (tested)
| Arena | Result |
|---|---|
| Reverse-split round-ups | ~$40-70 per brokerage account per month (§843) |
| Odd-lot tender offers | ~$2k/year (§732) |
| Going-private cash-outs | ~4 a year (§868) |
| IPO allocations, bank conversions, DRIP discounts, rights, spin-offs | Capital-bound or tiny (§842, §848) |

## C. Reselling (tested / desk)
| Arena | Realistic | Notes |
|---|---|---|
| Ticket resale | $300-700/month for beginners (seller claims) | Brokers lose on ~21% of tickets (NBER); scaling past purchase limits = BOTS Act risk |
| Pokémon sealed at MSRP | Break-even except hyped/preorder product | Access/bots game (§872) |
| MTG buylist arbitrage | A few % per cycle on capital | After ~8.25% TX sales tax and grading (§873) |
| LEGO retirement | ~11%/year (literature) | Capital, storage, slow |
| Amazon/Walmart retail arbitrage | 10-20% net margins | Effort; needs paid data |
| Domains | ~1-2% sell-through/year | Renewals ~$10/name/year |

## D. Paid work online (desk)
| Arena | Realistic pay | Notes |
|---|---|---|
| **AI automation freelancing (n8n/Zapier/agents/LLM apps)** | $25-50/hr entry, $60-150/hr specialised | AI-skill demand +109% YoY (Upwork 2026); entry tier crowded; Claude can do much of the build |
| AI training / data annotation | $15-25/hr general, $35-45/hr coding/STEM | Queues empty for weeks; accounts locked without notice; 1099 |
| Online tutoring | $15-20/hr (Varsity) to $35-75/hr (Wyzant, own rates) | Advanced subjects pay most |

## E. Build-and-sell (desk)
| Arena | Median outcome | Notes |
|---|---|---|
| Micro-SaaS / AI apps | Median $145/month; 70% < $1k MRR; 6% > $10k | 12-18 months to meaningful revenue |
| Digital products (Gumroad/Etsy) | Gumroad median ~$72/month; 44% of products $0 | Top 1% take most revenue |
| Faceless YouTube | $100-500/month for new monetised channels | "Inauthentic content" policy (2025) targets mass AI video |
| Affiliate / SEO sites | Search traffic −33%, position-1 CTR −58% with AI Overviews; Amazon commission cuts | Shrinking |
| Newsletters, courses | Audience-dependent | Slow |

## F. Crypto other (desk)
| Arena | Notes |
|---|---|
| Airdrop farming | Heavy sybil filtering (e.g. Linea removed ~800k wallets); no reliable retail-return data |
| Staking / yield | Capital-bound |

## G. Competitions and bounties (desk)
| Arena | Notes |
|---|---|
| OSS bug bounties | huntr left OSS bounties (report floods) |
| Data-science prizes | One active DrivenData prize ($300k); lumpy, compute-bound |

## Ranking for this user (start ~$100-200, scale past $2k/month)
1. **Tradeify plan** — already built; the one structural earner.
2. **AI automation freelancing** — $0 to start, $40-150/hr once specialised, demand rising; Claude does most of the build work. Time-bound, not passive.
3. **AI training work (coding tier)** — $35-45/hr if accepted at the coding tier; unstable supply of work.
4. Everything else: either capital-bound, a few hundred a month, shrinking, or excluded.
