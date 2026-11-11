"""MVTRX (SN79) market maker for the lab (futures-research decisions.md §1194).

Per book, every state update: fair = mid + MICRO·(microprice − mid) [+ FUND·(fundamental − mid) when the book publishes one]
− SKEW·(inventory as a fraction of the book's starting wealth)·spread. Quote one post-only order a side, at the best price or one tick
inside it, never through fair ± EDGE ticks; resting orders are replaced only when their price changes. Size SIZE × starting wealth
per side, cut to zero on the side that would push |inventory| past MAX_INV. Scored by the validator as two-sided making (balanced
capture vs a centred mid) and de-beta'd alpha (P&L net of inventory × the book's move), so the skew keeps inventory near flat.

    python QuoteAgent.py --port 8888 --agent_id 0 --params size=0.01 micro=1.0 skew=2.0 edge=1 max_inv=0.25 fund=0.0 expiry=60000000000 tape=/opt/mvtrx/tape.jsonl

tape=<path> (lab only): append every trade the state carries, per book, as {"ts", "book", "p", "q", "s", "Ma", "Ta", "Mf", "Tf"} plus one
{"ts", "book", "bid", "ask", "fund"} line per book per update, for the offline scorer (score_tape.py), which replays it through the
validator's own capture code.
"""

import json
import math
import os
import time
from collections import defaultdict

from taos.common.agents import launch
from taos.im.agents import FinanceAgent
from taos.im.protocol.models import OrderDirection, STP, TimeInForce
from taos.im.agents import ExchangeStateUpdate, UnifiedAccount
from taos.im.utils import duration_from_timestamp
import bittensor as bt


class _Ev:
    """An event / order from the raw wire dict (raw=1, §1207) under QuoteAgent's field names, built once with plain attributes: the
    pydantic build of the whole state (~9k resting orders + ~8k events) is most of our answer time, and the validator delays us by it."""
    __slots__ = ("y", "timestamp", "id", "price", "quantity", "side", "Ma", "Ta", "Mf", "Tf", "Mi")

    def __init__(self, d):
        g = d.get
        self.y, self.timestamp, self.id, self.price, self.quantity, self.side = g("y"), g("t"), g("i"), g("p"), g("q"), g("s")
        self.Ma, self.Ta, self.Mf, self.Tf, self.Mi = g("Ma"), g("Ta"), g("Mf"), g("Tf"), g("Mi")


class _Lv:
    __slots__ = ("price", "quantity")

    def __init__(self, d):
        self.price, self.quantity = d["p"], d["q"]


class _Bal:
    __slots__ = ("total", "free", "reserved", "initial")

    def __init__(self, d):
        self.total, self.free, self.reserved, self.initial = d.get("t"), d.get("f"), d.get("r"), d.get("i")


_LEVELS = 5


class _RawBook:
    __slots__ = ("bids", "asks", "events", "fundamental", "raw_b", "raw_a")

    def __init__(self, d):
        self.raw_b, self.raw_a = d.get("b") or [], d.get("a") or []    # levels with their resting orders in queue order (qlog)
        self.bids = [_Lv(x) for x in self.raw_b[:_LEVELS]]             # §1263: only the top 5 levels are ever read; building all of them was ≈ 10% of the handler
        self.asks = [_Lv(x) for x in self.raw_a[:_LEVELS]]
        self.events = [_Ev(x) for x in d.get("e") or []]
        self.fundamental = d.get("f")


class _RawAccount:
    __slots__ = ("base_balance", "quote_balance", "orders")

    def __init__(self, d):
        self.base_balance, self.quote_balance = _Bal(d.get("bb") or {}), _Bal(d.get("qb") or {})
        self.orders = [_Ev(x) for x in d.get("o") or []]


class QuoteAgent(FinanceAgent):
    def initialize(self):
        super().initialize()
        c = self.config
        self.size = float(getattr(c, "size", 0.01))
        self.micro = float(getattr(c, "micro", 1.0))
        self.fund = float(getattr(c, "fund", 0.0))
        self.fund_cap = float(getattr(c, "fund_cap", 0.0))   # §1378: >0: the fund lean is clipped to ±fund_cap × the book spread (unclipped it was ≈ 4 spreads on $300 books → one-sided quoting)
        self.fund_mv = float(getattr(c, "fund_mv", 0.0))           # §1379: >0: fair += fund_mv × (fundamental now − FUND_MV_S sim s ago) — a MOVE lean (the level is
        self.fund_mv_s = int(getattr(c, "fund_mv_s", 10))          # offset from mid for hours, §1379); clipped to ±FUND_MV_CAP spreads; $300 books only unless
        self.fund_mv_cap = float(getattr(c, "fund_mv_cap", 1.0))   # FUND_MV_VOL_ONLY = 0 (calm / 4-dec Δf does not predict mid cleanly)
        self.fund_mv_vol_only = int(getattr(c, "fund_mv_vol_only", 1))
        self._fh = {}
        self.skew = float(getattr(c, "skew", 2.0))
        self.edge = int(getattr(c, "edge", 1))
        self.max_inv = float(getattr(c, "max_inv", 0.25))
        self.expiry = int(getattr(c, "expiry", 60_000_000_000))
        self.join = int(getattr(c, "join", 0))          # 1: never step inside the best price, only join it
        self.flow = float(getattr(c, "flow", 0.0))       # fair += FLOW·spread·(signed taker-flow EMA / its absolute EMA), in [-1, 1]
        self.flow_decay = float(getattr(c, "flow_decay", 0.9))
        self._flow, self._absflow = {}, {}
        self.alpha_k = float(getattr(c, "alpha_k", 0.0))   # fair += ALPHA_K × the model's predicted 60 s mid change (signal_fit.py export)
        self.model = json.load(open(str(c.model))) if getattr(c, "model", "") else None
        self._oflow = {}                                    # per book: {sec: order-flow sums} (last 6 s), §1206
        self._mids, self._sflow = {}, {}                   # per book: {sec: mid} (last 125 s), {sec: signed taker qty} (last 6 s)
        self.trend_z = float(getattr(c, "trend_z", 0.0))   # >0: when the 120 s move exceeds TREND_Z standard deviations and inventory
                                                           # fights it, quote only the side that unwinds (§1194: losses sit on trending books)
        self.max_units = float(getattr(c, "max_units", 0.0))   # >0: hard position cap per book in base units (max_inv is a share of wealth and
                                                               # barely binds live: positions reached 285 units, §1199)
        self.back = int(getattr(c, "back", 0))             # >0: rest BACK ticks behind the best price on both sides: snipers take the
                                                           # touch; fills that reach deeper come from large sweeps that tend to revert (§1199)
        self.pull = float(getattr(c, "pull", 0.0))         # >0: drop the quote on the side the model says the price will cross (|pred| > PULL ticks):
                                                           # live, other miners snipe stale quotes at −8 ticks each (§1199)
        self.take = float(getattr(c, "take", 0.0))         # >0: also TAKE when |pred| > TAKE ticks: IOC at the opposite best price (§1211 add. 5:
                                                           # out of sample the 30 s gross edge is +2.4..+5.6 ticks per trade at 4 ticks; de-beta
                                                           # skill counts gross alpha, fees excluded; taker legs do not enter the making credit)
        self.take_size = float(getattr(c, "take_size", 10.0))   # units per take, capped by the top level's size and the position cap
        self.take_cool = int(getattr(c, "take_cool", 30))       # sim seconds between takes on one book
        self._last_take = {}
        self.own_ex = int(getattr(c, "own_ex", 0))         # 1: the order-flow features skip OUR orders / cancels (by order id) and our takes:
                                                           # at size 0.06 our own flow drove |pred| (§1211 add. 5: 30× the replay's takes)
        self._own_hist, self._own = [], set()
        self.own_stats = [0, 0, 0.0, 0.0]                  # [our o/c events skipped, all o/c events, our size, all size] (diagnostic)
        self.toxic = float(getattr(c, "toxic", 0.0))       # >0: pause a book while our fills' 30 s markout EMA is below −TOXIC ticks
        self.toxic_pause = int(getattr(c, "toxic_pause", 180))   # sim seconds the book stays paused
        self._pending, self._mo, self._paused = {}, {}, {}  # per book: [(due sec, side, price)], markout EMA (ticks), paused until sec
        sf = str(getattr(c, "skip_file", "") or "")         # file of book ids we never quote on: books whose fills stay picked off (§1211 add. 7:
        self.skip = {int(x) for x in open(sf).read().split()} if sf else set()
        self.skip_flat = int(getattr(c, "skip_flat", 0))
        self.fit_qty = int(getattr(c, "fit_qty", 0))
        self.tilt_bp = float(getattr(c, "tilt_bp", 0.0))   # >0: on quoted books the inventory target is ±TILT_NOTIONAL $ by the sign of (fundamental − mid)
        self.tilt_notional = float(getattr(c, "tilt_notional", 5000.0))   # beyond ±TILT_BP (hysteresis, re-checked every sleeve_step); skew and the
        self._tilt, self._tilt_at = {}, {}                 # unit caps act around it — de-beta skill on making books (§1211 add. 23)
        # pace (§1211 add. 21): the validator drops a miner's placements on a book once its traded notional over the last 24 sim h reaches
        # capital_turnover_cap (10) × miner wealth (≈ $500k per book). Quote a book only while the trailing PACE_PERIOD sum < PACE_CAP and the
        # trailing PACE_WIN sum < PACE_CAP × PACE_WIN / PACE_PERIOD × PACE_K (even spending). Seeded from our own tape at start-up.
        self.pace_cap = float(getattr(c, "pace_cap", 0.0)); self.pace_period = int(getattr(c, "pace_period", 86400))
        # §1255 TOKEN BUCKET, replacing the 90-sim-min window (which allowed a burst, then hours idle). Each book earns budget at RATE = PACE_CAP /
        # PACE_PERIOD per sim s, holds at most PACE_BURST sim s of it, and fills spend it (it may go negative). We quote / open only with a positive
        # balance. So over any PACE_PERIOD a book trades at most PACE_CAP + burst + one order set: < the validator's hard cap, for any fill pattern.
        # There is deliberately NO multiplier: the old pace_k override was how this got loosened by hand. pace_win / pace_k are ignored.
        self.pace_burst = float(getattr(c, "pace_burst", 900.0)); self.pace_rate = self.pace_cap / self.pace_period if self.pace_cap else 0.0
        # §1270 front-loaded start: a book with NO volume history starts with PACE_START dollars instead of a full burst, so a fresh UID can trade
        # faster while it climbs. The bucket never refills above the normal burst, so the extra is spent once. Choose pace_cap + pace_start + burst
        # under the validator's cap; use pace_steady to lower the refill rate while pace_cap stays the 24-h backstop (e.g. pace_cap 450,000, pace_steady 350,000, pace_start 100,000). Default 0: unchanged behaviour.
        self.pace_start = float(getattr(c, "pace_start", 0.0))
        self.pace_steady = float(getattr(c, "pace_steady", 0.0))   # §1270: >0: the refill rate's daily amount, separate from the 24-h backstop pace_cap
        if self.pace_cap and self.pace_steady > 0:
            self.pace_rate = self.pace_steady / self.pace_period
        self._tok = {}                                     # book -> [balance $, last sim s]
        self._val_vol = {}                                 # book -> the validator's traded_volume for this account, logged next to our ledger
        self._pace_logged = -10 ** 9
        if getattr(c, "pace_k", None) is not None or getattr(c, "pace_win", None) is not None:
            bt.logging.warning("pace_win / pace_k are ignored: pacing is a token bucket now (decisions.md §1255)")
        self._pace, self._pace_seen = defaultdict(list), set()
        pace_since = float(getattr(c, "pace_since", 0))   # sim s of our registration: the tape can hold a previous owner's fills on this UID (§1250)
        if self.pace_cap and getattr(c, "tape", "") and not getattr(c, "pace_ledger", ""):   # §1255: a ledger is the record; the tape holds a re-used UID's previous owner
            try:
                rows = []
                for line in open(str(c.tape)):
                    if '"p":' in line and str(self.uid) in line:
                        r = json.loads(line)
                        if r.get("Ma") == self.uid or r.get("Ta") == self.uid:
                            rows.append((r["ts"] // 1_000_000_000, r["book"], r["p"] * r["q"], (r["book"], r.get("id"), r["ts"])))
                end = max((x[0] for x in rows), default=0)
                for sec, bk, v, key in rows:
                    if sec > end - self.pace_period and sec >= pace_since and key not in self._pace_seen:
                        self._pace_seen.add(key); self._pace[bk].append((sec, v))
                bt.logging.info(f"PACE seeded {sum(len(v) for v in self._pace.values())} own fills on {len(self._pace)} books from the tape")
            except Exception as e:
                bt.logging.warning(f"PACE seed failed: {e}")
        # §1246: PACE_LEDGER = a file of our own fills (book, sec, notional, key), appended live and loaded at start, so a restart remembers the
        # validator's whole 24-sim-h volume window (≈ 5 wall days; the tape holds ≈ 20 wall h). If the sim clock is behind the ledger at the first
        # step (a new simulation), every stored entry is shifted back so the newest sits at that step (conservative: no gap is assumed).
        self.pace_ledger = str(getattr(c, "pace_ledger", "")).replace("UIDN", str(self.uid));   # UIDN → our uid: the cap is per UID, a new registration starts clean
        self._pace_shift_done = not self.pace_ledger; self._pace_last = None
        if self.pace_cap and self.pace_ledger and os.path.exists(self.pace_ledger):
            try:
                n0 = sum(len(v) for v in self._pace.values())
                off = 0; prev = None                       # lines are in append order: a sim reset shows as time jumping back; keep the timeline continuous
                for line in open(self.pace_ledger):
                    bk, sec, v, kid, kts = json.loads(line)
                    if prev is not None and sec + off < prev - 3600:
                        off = prev - sec
                    prev = sec + off
                    key = (bk, kid, kts)
                    if key not in self._pace_seen:
                        self._pace_seen.add(key); self._pace[bk].append((sec + off, v))
                for bk in self._pace: self._pace[bk].sort()
                bt.logging.info(f"PACE ledger added {sum(len(v) for v in self._pace.values()) - n0} fills from {self.pace_ledger}")
            except Exception as e:
                bt.logging.warning(f"PACE ledger load failed: {e}")
        if self.pace_cap:
            for bk, h in self._pace.items():                # replay the history through the bucket, so a restart resumes the same balance
                h.sort()
                for sec, v in h:
                    self._tok_spend(bk, sec, v)
        self.dbg = int(getattr(c, "dbg", 0)); self._dbg_at = {}   # 1: log per quoted book once a minute (inventory, balances, wanted sides)      # 1: quote the affordable part of the order instead of skipping the side (§1211 add. 21)
        self.sleeve_bp = float(getattr(c, "sleeve_bp", 0.0))   # >0 (with skip_flat): on skipped books steer the position to ±SLEEVE_Q by the sign of
        self.sleeve_q = float(getattr(c, "sleeve_q", 10.0))     # (fundamental − mid)/mid beyond ±SLEEVE_BP (hysteresis), checked every SLEEVE_STEP
        self.sleeve_step = int(getattr(c, "sleeve_step", 10))   # sim s, one IOC per SLEEVE_COOL s: de-beta skill counts held inventory × Δmid
        self.sleeve_cool = int(getattr(c, "sleeve_cool", 5))    # and its 2.3 bp hurdle is per own notional (§1211 add. 20)
        self._sleeve, self._sleeve_at = {}, {}
        self.rev_look = float(getattr(c, "rev_look", 0.0))       # >0: REVERSAL sleeve (§1223) on the sleeve books — when mid moved ≥ SLEEVE_BP over the
        self.rev_hold = float(getattr(c, "rev_hold", 180.0))     # last REV_LOOK sim s, steer the position to −sign(move) × REV_USD of notional, hold
        self.rev_usd = float(getattr(c, "rev_usd", 1000.0))      # REV_HOLD sim s, then back to flat (the top live-skill UIDs are 60-s faders)
        self.rev_skip_vol = int(getattr(c, "rev_skip_vol", 0))   # §1253: 1 = no NEW model entries on the volatile books (ids 0-62); open positions still exit
        self.rev_tp_bp = float(getattr(c, "rev_tp_bp", 0.0)); self._rev_px = {}   # §1258: >0: close a model position once the mid has moved this many bp in its favour; while one is open no new signal replaces it
        # §1267 scale-in: up to REV_LEGS equal clips of REV_USD per position. A new leg is added when the price has moved REV_LEG_BP from the last leg:
        # REV_LEG_DIR −1 = against us ("add to losers"), +1 = in our favour ("add to winners"), and only while the model still points the same way.
        # The profit target (rev_tp_bp) is then measured from the average leg price. Legs are new exposure, so pacing blocks them; exits always go.
        self.rev_legs = int(getattr(c, "rev_legs", 1)); self.rev_leg_bp = float(getattr(c, "rev_leg_bp", 6.0)); self.rev_leg_dir = int(getattr(c, "rev_leg_dir", -1))
        self._rev_n, self._rev_last = {}, {}
        # §1273 COPY mode (top skill takers, legs.py / legs2.py): each model signal that agrees with the open position (or a flat book) adds a burst of
        # REV_USD, up to REV_MAX_USD per book, sent as IOC clips of ≤ REV_CLIP_USD; while the mid is ≥ REV_TP_BP in favour of the AVERAGE entry,
        # sell REV_SLICE of the position at most once per REV_SLICE_COOL sim s; a remainder under REV_USD/2 closes. Opposite signals are ignored
        # (no stop), no clock exit. Adds are new exposure (paced); slices are exits (always go).
        self.rev_copy = int(getattr(c, "rev_copy", 0)); self.rev_max_usd = float(getattr(c, "rev_max_usd", 15000.0))
        self.rev_clip_usd = float(getattr(c, "rev_clip_usd", 0.0)); self.rev_slice = float(getattr(c, "rev_slice", 0.1))
        self.rev_slice_cool = float(getattr(c, "rev_slice_cool", 120.0)); self._slice_at = {}
        self.rev_copy_hold = float(getattr(c, "rev_copy_hold", 0.0)); self._legs = {}   # §1286: >0: each burst exits this many sim s after entry
        self.rev_th_k = float(getattr(c, "rev_th_k", 1.0))   # §1245: scale the fitted model's entry threshold (<1 = more entries)
        self.rev_rand = int(getattr(c, "rev_rand", 0))   # §1247 lab: 1 = model timing and size, RANDOM direction; 2 = the OPPOSITE of the model
        self._rev_rng = __import__("random").Random(int(getattr(c, "rev_seed", 7)))
        self.rev_imb = float(getattr(c, "rev_imb", -9.0))        # §1230: enter only when top-5 depth imbalance × our direction ≥ REV_IMB (off at -9)
        self.mk_model = str(getattr(c, "mk_model", "") or "")    # §1238: maker side — the same predictor guards our quotes
        self.mk_pull_bp = float(getattr(c, "mk_pull_bp", 0.0))   # >0: pull the quote on the side a forecast ≥ MK_PULL_BP (bp) says will lose
        # §1271 trend pull: when a book's mid has moved ≥ MK_TREND_BP over the last MK_TREND_WIN sim s, stop quoting the side facing the move
        # (rising: no offer; falling: no bid). 25 of x3's 65 books lost on the side facing their trend (median move 156 bp). 0 = off.
        self.mk_trend_bp = float(getattr(c, "mk_trend_bp", 0.0)); self.mk_trend_win = int(getattr(c, "mk_trend_win", 300)); self._mk_mid = {}; self._mkt_n = [0, 0]
        self.mk_vol_lad = [int(x) for x in str(getattr(c, "mk_vol_lad", "") or "").replace(":", ",").split(",") if x.strip()]   # §1278: ticks behind the touch, e.g. 2:5:10
        self.mk_vol_lazy = int(getattr(c, "mk_vol_lazy", 0))      # §1281: 1 = fleet pattern on the $300 books (one size, leave orders in place, penny wide spreads)
        self.mk_vol_penny = int(getattr(c, "mk_vol_penny", 5))    # §1281: quote one tick inside when the spread is ≥ this many ticks (fleet: 5+)
        self.mk_vol_keep = int(getattr(c, "mk_vol_keep", 20))     # §1281: keep resting orders up to this many ticks behind the target
        self.mk_vol_max = int(getattr(c, "mk_vol_max", 8))        # §1281: at most this many resting orders per side
        self.mk_tflow_usd = float(getattr(c, "mk_tflow_usd", 0.0))   # §1308: >0: on $300 books pull the bid while 10 s taker flow buys > this $ (pull the ask while it sells)
        self.mk_tflow_win = int(getattr(c, "mk_tflow_win", 10))        # §1308: trade-flow window, sim s
        self.mk_vol_inside = int(getattr(c, "mk_vol_inside", 0))   # §1304: >0: $300-book touch orders one tick inside the spread when it is ≥ this many ticks (fleet: 5)
        self.mk_calm_lad = [int(x) for x in str(getattr(c, "mk_calm_lad", "") or "").replace(":", ",").split(",") if x.strip()]   # §1303: calm-book ladder, ticks behind the touch (e.g. 1:2:4)
        self.mk_calm_lad_size = float(getattr(c, "mk_calm_lad_size", 0.036))   # §1303: calm ladder order size (fleet calm fills mostly $1-2k)
        self.mk_calm_expiry = int(float(getattr(c, "mk_calm_expiry", 0)) * 1_000_000_000)   # §1311: >0: calm-book (63-101) ladder orders expire after this many sim s (fleet: max 500 s, §1311); 0 = EXPIRY
        self.mk_dec_size = float(getattr(c, "mk_dec_size", 0.0))      # §1313: >0: fleet-style quoting on the 4-dec books (102-127), order size (fraction of wealth; fleet ≈ $4.5k ≈ 0.09)
        self.mk_dec_inside = int(getattr(c, "mk_dec_inside", 1))      # §1313: ticks ahead of OTHER makers' best price (fleet: 1-2 ticks = 51% of its 4-dec $); our own orders never count
        self.mk_dec_deep = float(getattr(c, "mk_dec_deep", 0.27))     # §1313: one deep order this many spreads behind the touch (fleet median 0.27, IQR 0.13-0.49)
        self.mk_calm_hold = int(getattr(c, "mk_calm_hold", 0))       # §1317: >0: calm ladder keeps a resting order up to this many ticks AHEAD of the target (fair / skew moved)
                                                                      # if it is not inside the others' best — fleet orders rest ≈ 107 s and get filled as the price comes to them
        self.mk_pace_hold = float(getattr(c, "mk_pace_hold", 0.0))   # §1317: >0: a paced-out CALM book keeps its orders ≥ 1 tick behind the others' best (touch / inside orders go,
        self.mk_nochase_bp = float(getattr(c, "mk_nochase_bp", 0.0))  # §1323: >0: if the own-side best moved AWAY by > this many bp over the last MK_NOCHASE_S sim s,
        self.mk_nochase_s = int(getattr(c, "mk_nochase_s", 10))        # quote at the best of MK_NOCHASE_S ago instead (order left behind, like the fleet's) — §1322:
                                                                        # 33% of our $300 $ filled right after re-joining a moved best (kept ≈ 0, move after −1.35 bp)
        self.mk_calm_touch_min = int(getattr(c, "mk_calm_touch_min", 0))   # §1323: >0: calm books place NO touch order while the others' spread is < this many ticks
        self.flow_pull_vol_only = int(getattr(c, "flow_pull_vol_only", 0))   # §1328: 1 = flow_pull acts only on the $300 books (0-62): there it kept x2 out of the
        self.mk_vol_touch_min = int(getattr(c, "mk_vol_touch_min", 0))   # §1334: >0: $300 books place NO touch order while the others' spread is < this many ticks
        self.live_params = str(getattr(c, "live_params", "") or "").replace("UIDN", str(getattr(self, "uid", "")))   # §1342: JSON file re-read live (no restart)
        self.live_params_s = int(getattr(c, "live_params_s", 30))       # §1342: sim seconds between checks of the file's mtime
        self._lp_mtime = None; self._lp_at = -10 ** 9
                                                                          # (fleet joins the $300 touch on only 16% of its $ vs x3 53%; ladder 2:5:10 stays)
                                                                              # after-move states (x4 without it lost ≈ 0.45 bp/fill); on calm books no pull won (+0.94)
        self._bbo = {}                                                      # (only the ladder behind it) — fleet calm edge comes from orders 1-3 behind the touch
                                                                      # nothing new is placed) while the bucket is above −this $ and the 24-h ledger is under pace_cap
        self.mk_thin_only_vol = int(getattr(c, "mk_thin_only_vol", 0))   # §1301: 1 = the thin-side rule applies ONLY on the $300 books (ids 0-62); calm/4-dec stay two-sided
        self.mk_calm_hs = float(getattr(c, "mk_calm_hs", 0.0))   # §1295: >0: calm books (63-101) quote this many half-spreads from the mid (fleet 1.67); 0 = off
        self.mk_max_ins = int(getattr(c, "mk_max_ins", 5))   # §1279: the validator keeps only this many instructions per book per reply (max_instructions_per_book, default 5)
        self.mk_vol_lad_size = float(getattr(c, "mk_vol_lad_size", 0.07))   # §1278: ladder order size on the $300 books (fraction of wealth; fleet ≈ $3.6k there)
        self.mk_thin_vol_off = int(getattr(c, "mk_thin_vol_off", 0))   # §1276: 1 = no thin-side pulls on the $300 books (ids 0-62)
        self.mk_vol_size = float(getattr(c, "mk_vol_size", 0.0))   # §1275: >0: maker order size (fraction of wealth) on the $300 books (ids 0-62) instead of SIZE
        self.mk_skip_vol = int(getattr(c, "mk_skip_vol", 0))   # §1247: 1 = no making on the volatile books (ids 0-62; quality -0.54 / -0.02 in both tape halves)
        self.mk_lad1 = float(getattr(c, "mk_lad1", 0.0)); self.mk_lad2 = float(getattr(c, "mk_lad2", 0.0))   # §1252: >0: extra resting orders this many spreads from the mid, on every side we quote (top makers fill at 0.5 / 1.5 / 3.5 spreads)
        self.mk_min_spread_bp = float(getattr(c, "mk_min_spread_bp", 0.0))   # §1242: >0: no quotes while the book's spread is under this (bp)
        self.mk_thin_ratio = float(getattr(c, "mk_thin_ratio", 0.0))         # §1242: >0: pull our side when its top size < RATIO × the other side's
        self._mkq_n = [0, 0, 0]                                   # [decisions, books skipped for spread, sides pulled as thin]
        self._mk_n = [0, 0]                                      # [quote sides pulled, quote decisions seen]
        self.rev_model = str(getattr(c, "rev_model", "") or "")  # §1233: path to the fitted predictor (rev_model.json); set = model entries
        self._rf = None
        if self.rev_model or self.mk_model:
            self.rev_model = self.rev_model or self.mk_model
            import os as _os, sys as _sys
            _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
            from revfeat import RevFeatures
            self._rf = RevFeatures(self.rev_model)
            pre = str(getattr(c, "rev_preload", "") or "")   # §1236: warm start from a live market tape on this box
            if pre:
                try:
                    n = self._rf.preload(pre, mb=int(getattr(c, "rev_preload_mb", 300)), own_uid=getattr(self, "uid", None))
                    bt.logging.info(f"REV PRELOAD: {n} snapshots from {pre}, {len(self._rf.books)} books warm")
                except Exception as ex:
                    bt.logging.warning(f"REV PRELOAD failed ({type(ex).__name__}: {ex}); warming up live")
                    self._rf = RevFeatures(self.rev_model)
        self._mid_hist, self._rev = {}, {}
        self.lock_dir = str(getattr(c, "lock_dir", "") or "")   # §1223: our UIDs must never trade with each other. A taker UID writes
        self.lock_hb_s = float(getattr(c, "lock_hb_s", 30.0))     # §1240: a maker heartbeat older than this (sim s) = that maker is down
        self.lock_max = float(getattr(c, "lock_max", 120.0))       # lock_<book>_<maker side> before its IOC; the maker UID pulls that side and
        self._lock_at = {}                                          # writes ack_<book>_<side> only once it has NO order left there; the taker
                                                                    # fires only on an ack at least as new as its lock, releases when done or after LOCK_MAX s
        self.sleeve_prop = float(getattr(c, "sleeve_prop", 0.0))   # >0: proportional sleeve — target = sleeve_q × clip(gap_bp / sleeve_prop, ±1),
        self.sleeve_band = float(getattr(c, "sleeve_band", 0.2))
        self.sleeve_dm = float(getattr(c, "sleeve_dm", 0.0))      # >0: use the gap minus its own EMA (half-life sleeve_dm sim s) — volatile books sit
        self.sleeve_sign = float(getattr(c, "sleeve_sign", 1.0))  # hundreds of bp from the fundamental; -1 trades WITH the deviation (§1211 add. 27)
        self._gap_ema = {}   # changed only when it moves > sleeve_band × sleeve_q (§1211 add. 27): de-beta
                                                                   # alpha comes from position CHANGES (a held position strips to zero)
        sb = str(getattr(c, "sleeve_file", "") or "")       # book ids the sleeve may trade (others in skip just unwind); unset = every skipped book
        self.sleeve_books = {int(x) for x in open(sb).read().split()} if sb else None   # 1: on skipped books, unwind the position with IOC takes (taker fills never enter the
                                                           # making pool, takers get a fee rebate) — one take per take_cool, ≤ take_size, ≤ top level   # books ranked on one half lift the other half 0.03 → 0.22)
        self.tape = open(str(c.tape), "a") if getattr(c, "tape", "") else None
        self.lean = int(getattr(c, "lean", 0))             # 1: skip the base agent's state history, CSV event log and debug text (§1207, speed)
        self.cancel_first = int(getattr(c, "cancel_first", 0))   # 1: cancel the side the prediction says is exposed first (§1207)
        self.flow_pull = float(getattr(c, "flow_pull", 0.0))   # >0: drop our offer while near-touch new-order imbalance (5 s) > FLOW_PULL, our
        self._near = {}                                    # bid while < -FLOW_PULL; fills there average −2 ticks from anyone (pull_scan.py, §1207)
        self.flow_win = int(getattr(c, "flow_win", 5))     # seconds of near-touch order flow behind flow_pull
        self.flow_cool = int(getattr(c, "flow_cool", 0))   # seconds a side stays pulled after flow_pull last fired (backoff_scan.py: 10 s window +
        self._pull_until = {}                              # 3 s cooldown ≈ break-even out of sample vs −0.16 for 5 s / none)
        self.sticky = int(getattr(c, "sticky", 0))         # >0: keep a resting order when the target moves up to STICKY ticks more aggressive than
                                                           # it — a re-placed order joins the back of the queue and fills only when the level is
                                                           # being swept: 62% of our fills vs 41% of the field's, at −3 ticks (§1207)
        self.snap = int(getattr(c, "snap", 0))             # 1: move each quote to the nearest price another maker already holds (never alone)
        self.qlog = int(getattr(c, "qlog", 0))
        # arms="edge:2/edge:3/flow_pull:0.3+flow_win:10+flow_cool:3": per-book A/B in one run (no "=" — the miner's param parser splits on it).
        # Arm 0 is the configured params; arm k (1..K) overrides on books with book_id mod (K + 1) == k. Same window for every arm (§1207).
        self._arms = [{}]
        for spec in str(getattr(c, "arms", "") or "").split("/"):
            if spec.strip():
                ov = {}
                for kv in spec.split("+"):
                    k, v = kv.split(":")
                    cur = getattr(self, k)                 # unknown names fail loudly at start-up
                    ov[k] = type(cur)(float(v)) if isinstance(cur, (int, float)) and not isinstance(cur, bool) else v
                self._arms.append(ov)
        if len(self._arms) == 1:
            self._arms = []             # 1 (raw mode, tape on): log each of our orders' size ahead in its queue per update
        self.raw = int(getattr(c, "raw", 0))               # 1 (with lean=1 lazy_load=1): read books / our accounts from the raw wire dicts, §1207
        self._books = None

    def update(self, state):
        """lean=1: only what QuoteAgent reads (config, our accounts, our notices). The base update copies every state into a
        history, writes every order / cancel / trade to CSV (reloaded on restart, §1207) and formats a debug dump of every book;
        QuoteAgent uses none of it and the validator delays our orders by how long we take."""
        if not self.lean or isinstance(state, ExchangeStateUpdate):
            return super().update(state)
        self.simulation_config = state.config
        raw_books = getattr(state.books, "_raw_books", None)
        if self.raw and raw_books is not None:            # lazy_load=1 left the wire dicts in place
            self._books = {bid: _RawBook(d) for bid, d in raw_books.items()}
            self.accounts = {int(bid): _RawAccount(d) for bid, d in state.accounts._raw_accounts[self.uid].items()}
        else:
            self._books = None
            self.accounts = {bid: UnifiedAccount(a) for bid, a in state.accounts[self.uid].items()}
        self.events = list(state.notices[self.uid])
        self._exchange_mode = False
        for e in self.events:
            if e.type in ("EVENT_SIMULATION_START", "ESS"):
                self.onStart(e)
            elif e.type in ("EVENT_SIMULATION_END", "ESE"):
                self.onEnd(e)
        bt.logging.info(f"VALIDATOR : {state.dendrite.hotkey} | SIMULATION TIME : {duration_from_timestamp(state.timestamp)} (T={state.timestamp})")

    def respond_simulation(self, state):
        response = self.make_response()
        self._sec = state.timestamp // 1_000_000_000
        self._clock_check()
        if self.live_params:
            self._live_reload()
        if self.lock_dir and len(self.skip) < 128 and self._sec != getattr(self, "_hb_at", None):
            self._hb_at = self._sec                            # §1240 maker heartbeat: takers only handshake while a maker of ours is alive
            hb = f"{self.lock_dir}/maker_{self.uid}.hb"
            with open(hb + ".tmp", "w") as fh:
                fh.write(str(self._sec))
            os.replace(hb + ".tmp", hb)
        if self.own_ex:                                    # ids of our resting orders in this and the last 2 states: an order we placed rests
            self._own_hist.append({o.id for a in self.accounts.values() for o in (a.orders or [])})   # at least one state before its cancel
            self._own_hist = self._own_hist[-3:]; self._own = set().union(*self._own_hist)
            if self._sec % 60 == 0 and self.own_stats[1]:
                n, t, q, qt = self.own_stats
                bt.logging.info(f"OWN FLOW: our share of order/cancel events {n / t:.1%} by count, {q / max(qt, 1e-9):.1%} by size")
        if self._sec - getattr(self, "_ioc_logged", -10 ** 9) >= 60 and getattr(self, "_ioc_n", 0):
            self._ioc_logged = self._sec            # §1223 add. 6: x2 runs without a tape, so log its IOC flow once per sim minute
            bt.logging.info(f"IOC FLOW: {self._ioc_n} IOCs, ${self._ioc_usd:,.0f} since start; rev targets open {sum(1 for t, _ in self._rev.values() if t)}; model entries {getattr(self, '_model_n', 0)}; copy slices {getattr(self, '_slice_n', 0)}")
        if self.tape is not None:
            self._record(state)
        if self.pace_cap:
            for book_id, book in (self._books if self._books is not None else state.books or {}).items():
                for e in book.events or []:
                    if getattr(e, "y", "") == "t" and (e.Ma == self.uid or e.Ta == self.uid):
                        key = (int(book_id), e.id, e.timestamp)
                        if key not in self._pace_seen:
                            self._pace_seen.add(key); self._pace[int(book_id)].append((e.timestamp // 1_000_000_000, e.price * e.quantity))
                            self._tok_spend(int(book_id), e.timestamp // 1_000_000_000, e.price * e.quantity)
                            if self.pace_ledger:
                                try:
                                    with open(self.pace_ledger, "a") as fh:
                                        fh.write(json.dumps([int(book_id), e.timestamp // 1_000_000_000, e.price * e.quantity, e.id, e.timestamp]) + "\n")
                                except Exception:
                                    pass
            newest = max((h[-1][0] for h in self._pace.values() if h), default=None)
            if newest is not None and (not self._pace_shift_done or (self._pace_last is not None and self._sec < self._pace_last - 60)):
                if newest > self._sec + 60:                  # the sim clock went backwards (new simulation): keep the volume, shift its times
                    d = self._sec - newest
                    for bk in self._pace: self._pace[bk] = [(t + d, v) for t, v in self._pace[bk]]
                    for st in self._tok.values(): st[1] += d
                    bt.logging.info(f"PACE clock shift {d} s")
                self._pace_shift_done = True
            self._pace_last = self._sec
            if self._sec - self._pace_logged >= 60:
                self._pace_logged = self._sec
                self._pace_status()
        for book_id, book in (self._books if self._books is not None else state.books or {}).items():
            acct = self.accounts.get(book_id)
            if acct is None or not book.bids or not book.asks:
                continue
            try:
                self._quote(response, book_id, book, acct)
            except Exception as ex:                        # §1223 add. 7: never swallow silently — count and log once per sim minute
                self._qerr = getattr(self, "_qerr", 0) + 1
                if self._sec - getattr(self, "_qerr_at", -10 ** 9) >= 60:
                    self._qerr_at = self._sec
                    import traceback
                    bt.logging.warning(f"QUOTE ERROR x{self._qerr} book {book_id}: {type(ex).__name__}: {ex} | {traceback.format_exc(limit=3)[-400:]}")
                continue
        try:                                               # §1292: which books send > 5 instructions in one reply (the validator drops the excess)
            from collections import Counter
            cnt = Counter(getattr(i, "bookId", None) for i in (response.instructions or []))
            over = {b: n for b, n in cnt.items() if n > 5}
            if over:
                self._ins_over = getattr(self, "_ins_over", Counter()); self._ins_over.update({("$300" if b < 63 else "calm" if b < 102 else "4dec"): n - 5 for b, n in over.items()})
                self._ins_ex = getattr(self, "_ins_ex", {}); self._ins_ex.update({b: [type(i).__name__ for i in response.instructions if getattr(i, "bookId", None) == b] for b in list(over)[:1]})
            if self._sec - getattr(self, "_ins_logged", -10 ** 9) >= 60 and getattr(self, "_ins_over", None):
                self._ins_logged = self._sec
                bt.logging.info(f"INS OVER 5: excess by book group {dict(self._ins_over)} | example {self._ins_ex}")
                self._ins_over.clear(); self._ins_ex = {}
        except Exception:
            pass
        return response

    def _predict(self, book_id, book, sec, mid):
        """The signal_fit features, live: taker flow 5 s, returns 5/30/120 s, depth imbalance L1/L5, microprice − mid (§1194)."""
        mids = self._mids.setdefault(book_id, {}); fl = self._sflow.setdefault(book_id, {})
        ofl = self._oflow.setdefault(book_id, {})       # {sec: [new bid, new ask, near-touch new bid, near-touch new ask, cancelled bid, cancelled ask]}
        mids[sec] = mid
        tick = 10.0 ** -self.price_decimals(book_id)
        b0, a0 = book.bids[0].price, book.asks[0].price
        row = ofl.setdefault(sec, [0.0] * 6)
        for e in book.events or []:
            kind = getattr(e, "y", "")
            if self.own_ex and kind in ("o", "c"):
                self.own_stats[1] += 1; self.own_stats[3] += e.quantity or 0.0
                if e.id in self._own:
                    self.own_stats[0] += 1; self.own_stats[2] += e.quantity or 0.0
                    continue
            if kind == "t" and self.own_ex and e.Ta == self.uid:
                continue
            if kind == "t":
                s = e.timestamp // 1_000_000_000
                fl[s] = fl.get(s, 0.0) + e.quantity * (1 if e.side == 0 else -1)
            elif kind == "o" and e.price is not None:
                bid_side = e.side == 0
                row[0 if bid_side else 1] += e.quantity
                if (bid_side and e.price >= b0 - 2 * tick) or (not bid_side and e.price <= a0 + 2 * tick):
                    row[2 if bid_side else 3] += e.quantity
            elif kind == "c" and getattr(e, "side", None) is not None:   # pydantic Cancellation has no side (x2 crash 11-05)
                row[4 if e.side == 0 else 5] += e.quantity or 0.0
        for d, keep in ((mids, 125), (fl, max(6, self.mk_tflow_win + 1)), (ofl, max(6, self.flow_win + 1))):   # §1308: trade flow kept for the trade-flow pull window
            for s in [s for s in d if s < sec - keep]:
                del d[s]
        nb2, na2 = (sum(ofl.get(sec - j, [0.0] * 6)[i] for j in range(self.flow_win)) for i in (2, 3))
        self._near[book_id] = (nb2 - na2) / (nb2 + na2) if nb2 + na2 > 0 else 0.0   # near-touch new-order imbalance, 5 s (flow_pull)
        if sec - 120 not in mids:
            return 0.0
        b, a = book.bids, book.asks
        def imb(k):
            bq, aq = sum(l.quantity for l in b[:k]), sum(l.quantity for l in a[:k])
            return (bq - aq) / (bq + aq) if bq + aq else 0.0
        micro = (b[0].price * a[0].quantity + a[0].price * b[0].quantity) / (b[0].quantity + a[0].quantity) - mid
        o5 = [sum(ofl.get(sec - j, [0.0] * 6)[i] for j in range(5)) for i in range(6)]
        ratio = lambda x, y: (x - y) / (x + y) if x + y > 0 else 0.0
        feats = {"flow5": sum(fl.get(sec - j, 0.0) for j in range(5)), "ret5": mid - mids.get(sec - 5, mid), "ret30": mid - mids.get(sec - 30, mid),
                 "ret120": mid - mids[sec - 120], "imb1": imb(1), "imb5": imb(5), "micro": micro,
                 "of_new": ratio(o5[0], o5[1]), "of_near": ratio(o5[2], o5[3]), "of_cancel": ratio(o5[5], o5[4])}   # §1206 order flow
        m = self.model
        x = [feats[n] for n in m["names"]]
        return sum(w * (v - mu) / sd for w, v, mu, sd in zip(m["w"], x, m["mu"], m["sd"]) if sd > 0)

    def onOrderRejected(self, event):
        """dbg: count the exchange's placement rejections by message, logged once a minute (§1211 add. 21)."""
        if not getattr(self, "dbg", 0):
            return
        from collections import Counter
        self._rej = getattr(self, "_rej", Counter()); self._rej[str(getattr(event, "message", "?"))] += 1
        if self._sec - getattr(self, "_rej_at", -10 ** 9) >= 60:
            self._rej_at = self._sec; bt.logging.info(f"DBG REJECTS {dict(self._rej)}"); self._rej.clear()

    def _rev_leg(self, book_id, tgt, mid):
        """§1267: add one more equal clip to an open model position when the price has moved REV_LEG_BP from the last leg in the chosen direction
        and the model still agrees; the average price for the target follows."""
        n = self._rev_n.get(book_id, 1); last = self._rev_last.get(book_id)
        if n >= self.rev_legs or not last:
            return tgt
        sg = 1.0 if tgt > 0 else -1.0; move = sg * (mid - last) / last * 1e4
        if not (move <= -self.rev_leg_bp if self.rev_leg_dir < 0 else move >= self.rev_leg_bp):
            return tgt
        pr = self._rf.predict(int(book_id), self._sec) if self._rf is not None else None
        if pr is None or pr * sg <= 0:
            return tgt
        n += 1; self._rev_n[book_id] = n; self._rev_last[book_id] = mid
        self._rev_px[book_id] = (self._rev_px.get(book_id, mid) * (n - 1) + mid) / n
        self._legs_n = getattr(self, "_legs_n", 0) + 1
        return tgt + sg * self.rev_usd / mid

    def _tflow_usd(self, book_id, mid):
        """§1308: signed taker $ over the last MK_TFLOW_WIN sim seconds (+ = takers buying, i.e. hitting the asks), from the per-second _sflow history."""
        fl = self._sflow.get(book_id, {})
        return sum(v for s, v in fl.items() if s > self._sec - self.mk_tflow_win) * mid

    def _calm_px(self, bid, ask, tick, pd, bid_px, ask_px):
        """§1295: quote prices MK_CALM_HS half-spreads from the mid, rounded AWAY from the mid, never more aggressive than the normal target
        (bid_px / ask_px). Long-lived fleet 5F1F2JMu on calm books: fills 1.67 half-spreads out, edge +7.8 bp vs our +3.2 at the touch."""
        mid = (bid + ask) / 2; hs = (ask - bid) / 2; k = self.mk_calm_hs
        tb = round(math.floor((mid - k * hs) / tick + 0.05) * tick, pd); ta = round(math.ceil((mid + k * hs) / tick - 0.05) * tick, pd)   # 5% of a tick: 5.01 ticks counts as 5
        nb = None if bid_px is None else (min(bid_px, tb) if tb > 0 else bid_px)
        na = None if ask_px is None else max(ask_px, ta)
        self._calm_n = getattr(self, "_calm_n", 0) + 1
        return nb, na

    def _cancel_all(self, response, book_id, orders):
        """§1293: pull several of our orders with ONE CancelOrders instruction. One cancel per order went over the validator's 5 instructions per book
        per reply on the $300 ladder books (7-8 cancels when a book paced out) — the excess was dropped and those orders stayed on the book."""
        ids = [o.id for o in (orders or [])]
        if len(ids) == 1:
            response.cancel_order(book_id, ids[0])
        elif ids:
            response.cancel_orders(book_id, ids)

    def _vol_lazy(self, response, book_id, orders, want, vq, tick, pd):
        """§1281: the long-lived fleet's $300-book pattern, inferred from its fills. One order size (MK_VOL_LAD_SIZE, ≈ $3.6k) placed at the touch
        (WANT, computed without our own size) or one tick INSIDE when the spread is ≥ MK_VOL_PENNY ticks; when the price moves away the order is LEFT
        in place (kept up to MK_VOL_KEEP ticks behind the target, at most MK_VOL_MAX per side, deepest cancelled first). Same 5-instruction budget and
        priority as _vol_ladder: exposed cancels, new touch orders, over-limit / too-deep cancels."""
        B, S = OrderDirection.BUY, OrderDirection.SELL
        tgt = dict(want)
        if B in tgt and S in tgt and self.mk_vol_penny and round((tgt[S] - tgt[B]) / tick) >= self.mk_vol_penny:
            tgt[B] = round(tgt[B] + tick, pd); tgt[S] = round(tgt[S] - tick, pd)
        n = sum(1 for i in (response.instructions or []) if getattr(i, "bookId", None) == book_id)
        urgent, stale, have, rest = [], [], set(), {B: [], S: []}
        for o in orders:
            px = tgt.get(o.side)
            if px is None:
                urgent.append(o); continue
            behind = round(((px - o.price) if o.side == B else (o.price - px)) / tick, 6)
            if behind < 0:
                urgent.append(o)                          # ahead of the target (the touch moved against it): exposed
            elif behind > self.mk_vol_keep:
                stale.append(o)
            else:
                rest[o.side].append((behind, o))
                if behind == 0: have.add(o.side)
        for side, lst in rest.items():                    # over MK_VOL_MAX resting on a side (room kept for a new touch order): cancel the deepest first
            lst.sort(key=lambda x: x[0])
            limit = self.mk_vol_max - (1 if side in tgt and side not in have else 0)
            if len(lst) > limit:
                stale.extend(o for _, o in reversed(lst[limit:]))
        for o in urgent:
            if n >= self.mk_max_ins: return
            response.cancel_order(book_id, o.id); n += 1
        for side, px in tgt.items():
            if side in have: continue
            if n >= self.mk_max_ins: return
            response.limit_order(book_id=book_id, direction=side, quantity=vq, price=px, stp=STP.CANCEL_BOTH, postOnly=True,
                                 timeInForce=TimeInForce.GTT, expiryPeriod=self.expiry); n += 1
        for o in stale:
            if n >= self.mk_max_ins: return
            response.cancel_order(book_id, o.id); n += 1

    # §1342 live settings: quoting knobs only. Pacing / cap / ledger settings are NEVER live-changeable (cap safety); list parameters (ladders) neither.
    LIVE_KNOBS = {"flow_pull": float, "flow_pull_vol_only": int, "flow_win": int, "flow_cool": int, "mk_vol_inside": int, "mk_vol_touch_min": int,
                  "mk_nochase_bp": float, "mk_nochase_s": int, "mk_calm_touch_min": int, "mk_calm_hold": int, "mk_pace_hold": float,
                  "mk_vol_size": float, "mk_vol_lad_size": float, "mk_calm_lad_size": float, "mk_dec_size": float, "mk_dec_inside": int,
                  "mk_dec_deep": float, "mk_thin_ratio": float, "mk_thin_only_vol": int, "mk_thin_vol_off": int, "skew": float, "mk_calm_expiry": float,
                  "fund": float, "fund_cap": float, "fund_mv": float, "fund_mv_cap": float, "micro": float, "mk_skip_vol": int}   # §1373: 1 = no making on the $300 books (miner-wide quality test)   # §1369: fundamental lean (the fleet fills after fundamental moves its way, §1368) and the micro-price weight
    LIVE_LISTS = {"mk_calm_lad": (1, 20, 4), "mk_vol_lad": (1, 20, 4)}   # §1346: ladder levels "a:b:c" — ticks 1..20, at most 4 levels (5-instruction budget)
    LIVE_LIMITS = {"mk_pace_hold": (0.0, 10000.0), "mk_vol_size": (0.0, 0.1), "mk_vol_lad_size": (0.0, 0.1), "mk_calm_lad_size": (0.0, 0.1),
                   "mk_dec_size": (0.0, 0.12), "skew": (0.0, 30.0), "mk_calm_expiry": (0.0, 3600.0), "fund": (0.0, 1.0), "fund_cap": (0.0, 5.0), "fund_mv": (0.0, 2.0), "fund_mv_cap": (0.0, 5.0), "micro": (0.0, 1.0)}

    def _live_reload(self):
        """§1342: every LIVE_PARAMS_S sim s, if the JSON file changed, apply whitelisted quoting knobs (type-cast, range-checked) without a restart.
        Anything else in the file is ignored; a bad file changes nothing. Every change is logged."""
        if self._sec - self._lp_at < self.live_params_s and self._lp_at <= self._sec:
            return
        self._lp_at = self._sec
        try:
            m = os.path.getmtime(self.live_params)
        except OSError:
            return
        if m == self._lp_mtime:
            return
        self._lp_mtime = m
        try:
            with open(self.live_params) as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
        except Exception as e:
            bt.logging.warning(f"LIVE PARAMS: {self.live_params} unreadable ({e}) — nothing changed")
            return
        changed, ignored = [], []
        for k, v in data.items():
            if k in self.LIVE_LISTS:
                lo_, hi_, mx = self.LIVE_LISTS[k]
                try:
                    lv = [int(x) for x in str(v).replace(",", ":").split(":") if str(x).strip()]
                except ValueError:
                    ignored.append(k); continue
                if not lv or len(lv) > mx or any(not (lo_ <= x <= hi_) for x in lv) or len(set(lv)) != len(lv):
                    ignored.append(f"{k}(bad levels)"); continue
                lv = sorted(lv); old = getattr(self, k, None)
                if old != lv:
                    setattr(self, k, lv); changed.append(f"{k} {old}→{lv}")
                continue
            typ = self.LIVE_KNOBS.get(k)
            if typ is None:
                ignored.append(k); continue
            try:
                nv = typ(v)
            except (TypeError, ValueError):
                ignored.append(k); continue
            lo, hi = self.LIVE_LIMITS.get(k, (None, None))
            if lo is not None and not (lo <= nv <= hi):
                ignored.append(f"{k}(out of range)"); continue
            if k == "mk_calm_expiry":
                nv = int(nv * 1_000_000_000)                 # stored in ns
            old = getattr(self, k, None)
            if old != nv:
                setattr(self, k, nv); changed.append(f"{k} {old}→{nv}")
        bt.logging.info(f"LIVE PARAMS applied: {', '.join(changed) or 'no change'}" + (f" | ignored: {', '.join(ignored)}" if ignored else ""))

    def _fund_shift(self, fundamental, mid, spread):
        """§1369/§1378: fair-price lean toward the fundamental = fund × (fundamental − mid), clipped to ±fund_cap × spread when fund_cap > 0."""
        sh = self.fund * (fundamental - mid)
        if self.fund_cap > 0:
            lim = self.fund_cap * spread
            sh = max(-lim, min(lim, sh))
        return sh

    def _fund_rec(self, book_id, f):
        """§1379: the fundamental per sim second for every book; keeps the newest sample at least FUND_MV_S old at h[0]."""
        if not f:
            return
        h = self._fh.setdefault(book_id, [])
        if not h or h[-1][0] != self._sec:
            h.append((self._sec, f))
        while len(h) > 1 and h[1][0] <= self._sec - self.fund_mv_s:
            h.pop(0)

    def _fund_mv_shift(self, book_id, spread):
        """§1379: fund_mv × (fundamental now − FUND_MV_S s ago), clipped to ±FUND_MV_CAP × spread; 0 without a full window or off-book-group."""
        if self.fund_mv_vol_only and book_id >= 63:
            return 0.0
        h = self._fh.get(book_id)
        if not h or len(h) < 2 or h[0][0] > self._sec - self.fund_mv_s or spread <= 0:
            return 0.0
        sh = self.fund_mv * (h[-1][1] - h[0][1])
        lim = self.fund_mv_cap * spread
        return max(-lim, min(lim, sh))

    def _bbo_rec(self, book_id, bid, ask):
        """§1326: the best bid/ask per sim second for every book, recorded EVERY round before the pace gate (paced-out books had no history, so the
        cap never fired when a book came back — exactly when new orders go in). Keeps the newest sample at least MK_NOCHASE_S old at h[0]."""
        h = self._bbo.setdefault(book_id, [])
        if not h or h[-1][0] != self._sec:
            h.append((self._sec, bid, ask))
        while len(h) > 1 and h[1][0] <= self._sec - self.mk_nochase_s:
            h.pop(0)
        return h

    def _nochase(self, book_id, want, bid, ask, mid, pd):
        """§1323: record the book's best each sim second; if the bid rose (ask fell) by > MK_NOCHASE_BP over the last MK_NOCHASE_S s, cap our bid at the
        bid of then (floor our ask at the ask of then): we stay where the price was instead of chasing it. Returns the number of sides capped."""
        h = self._bbo_rec(book_id, bid, ask)
        if h[0][0] > self._sec - self.mk_nochase_s:
            return 0
        _, b0, a0 = h[0]; lim = self.mk_nochase_bp * mid / 1e4; n = 0
        if OrderDirection.BUY in want and bid - b0 > lim and want[OrderDirection.BUY] > b0:
            want[OrderDirection.BUY] = round(b0, pd); n += 1
        if OrderDirection.SELL in want and a0 - ask > lim and want[OrderDirection.SELL] < a0:
            want[OrderDirection.SELL] = round(a0, pd); n += 1
        return n

    @staticmethod
    def _others_best(book, orders):
        """§1313: best bid / ask held by OTHER participants (our own resting quantity removed level by level), so stepping inside never chases our own order."""
        ours = defaultdict(float)
        for o in orders:
            ours[(int(o.side), o.price)] += o.quantity or 0.0
        ob = next((l.price for l in (book.bids or []) if (l.quantity or 0.0) - ours.get((0, l.price), 0.0) > 1e-9), None)
        oa = next((l.price for l in (book.asks or []) if (l.quantity or 0.0) - ours.get((1, l.price), 0.0) > 1e-9), None)
        return ob, oa

    def _dec_targets(self, book, orders, want, tick, pd):
        """§1313 fleet 4-dec pattern: a side still wanted AT the touch moves MK_DEC_INSIDE ticks ahead of the others' best (never crossing); a side the
        inventory skew already put behind the touch stays where it is. Returns the deep level in ticks (MK_DEC_DEEP spreads, ≥ 3) or None."""
        B, S = OrderDirection.BUY, OrderDirection.SELL
        ob, oa = self._others_best(book, orders)
        if ob is None or oa is None or oa - ob < 3 * tick - 1e-12:
            return None
        n = self.mk_dec_inside * tick
        if B in want and want[B] >= ob - 1e-12:
            want[B] = round(min(ob + n, oa - tick), pd)
        if S in want and want[S] <= oa + 1e-12:
            want[S] = round(max(oa - n, ob + tick), pd)
        if B in want and S in want and want[B] >= want[S] - 1e-12:
            want[B], want[S] = ob, oa
        return max(3, round(self.mk_dec_deep * (oa - ob) / tick)) if self.mk_dec_deep > 0 else None

    def _vol_ladder(self, response, book_id, orders, want, sq, qty, vq, tick, pd, levels=None, inside=0, expiry=None, tol=None, obest=None, hold=0, no_touch=False):
        """§1279: $300-book quoting. Touch orders at WANT; ladder orders REST anywhere 1..max(MK_VOL_LAD)+2 ticks behind the touch target (no re-pricing
        when the touch moves, so they keep their queue place). The validator accepts only MK_MAX_INS instructions per book per reply (default 5;
        the rest are DROPPED), so instructions go in priority order: (1) cancel orders ahead of the target or on a pulled side, (2) touch orders,
        (3) cancel orders too far behind, (4) missing ladder levels, nearest first."""
        B, S = OrderDirection.BUY, OrderDirection.SELL
        levels = levels or self.mk_vol_lad
        if inside and obest is not None and B in want and S in want:   # §1314: step inside the OTHER makers' best, never our own order (the §1304 version
            ob, oa = obest                                                # pennied itself round after round: 8-tick spreads walked to 4, walk300.py)
            if ob is not None and oa is not None and round((oa - ob) / tick) >= inside:
                nb = round(ob + tick, pd) if want[B] >= ob - 1e-12 else want[B]   # a side the skew put behind the touch stays put
                na = round(oa - tick, pd) if want[S] <= oa + 1e-12 else want[S]
                if nb < na - 1e-12: want[B], want[S] = nb, na
        elif inside and B in want and S in want and round((want[S] - want[B]) / tick) >= inside:   # §1304 fleet: one tick INSIDE the spread when it is ≥ INSIDE ticks wide
            want[B] = round(want[B] + tick, pd); want[S] = round(want[S] - tick, pd)
        tgt = dict(want); span = max(levels) + (2 if tol is None else max(2, tol))   # §1313: a wide tolerance widens the keep window too
        if no_touch:
            want = {}                                     # §1323: ladder only — touch orders are not placed (and a resting one is cancelled below)
        n = sum(1 for i in (response.instructions or []) if getattr(i, "bookId", None) == book_id)
        urgent, stale, keep = [], [], {B: [], S: []}
        for o in orders:
            px = tgt.get(o.side)
            if px is None:
                urgent.append(o); continue
            behind = round(((px - o.price) if o.side == B else (o.price - px)) / tick, 6)
            if behind == 0 and no_touch:
                urgent.append(o)                          # §1323: no touch order on this book right now
            elif behind == 0 and o.side in want:
                want.pop(o.side)                          # touch order already resting at the target
            elif 1 <= behind <= span and (tol is None or any(abs(behind - lv_) <= tol for lv_ in levels)):
                keep[o.side].append(behind)               # resting ladder order: keep its queue place (§1332: with a wide tolerance only near a level —
                                                          # 4-dec touch orders left behind by a move piled up, 7 on one book, 8 instructions)
            elif behind < 0 and hold and behind >= -hold and o.side in want and obest is not None and (
                    (o.side == B and obest[0] is not None and o.price <= obest[0] + 1e-12) or (o.side == S and obest[1] is not None and o.price >= obest[1] - 1e-12)):
                want.pop(o.side)                          # §1317: the target moved behind it by ≤ HOLD ticks and it is not inside the others' best: keep it as our touch order
            elif behind < 0:
                urgent.append(o)                          # ahead of the target: exposed, cancel first
            else:
                stale.append(o)
        for o in urgent:
            if n >= self.mk_max_ins: break
            response.cancel_order(book_id, o.id); n += 1
        for side, px in want.items():
            if n >= self.mk_max_ins: break
            response.limit_order(book_id=book_id, direction=side, quantity=sq.get(side, qty), price=px, stp=STP.CANCEL_BOTH, postOnly=True,
                                 timeInForce=TimeInForce.GTT, expiryPeriod=expiry or self.expiry); n += 1
        for o in stale:
            if n >= self.mk_max_ins: break
            response.cancel_order(book_id, o.id); n += 1
        lv = sorted(levels)
        if tol is None: tol = min((y - x for x, y in zip(lv, lv[1:])), default=2) // 2   # §1303: 1:2:4 → 0 (adjacent levels), 2:5:10 → 1
        for k in lv:
            for side, px in tgt.items():
                if n >= self.mk_max_ins: return
                if any(abs(b - k) <= tol for b in keep[side]): continue
                p = round(px - k * tick if side == B else px + k * tick, pd)
                if p <= 0: continue
                response.limit_order(book_id=book_id, direction=side, quantity=vq, price=p, stp=STP.CANCEL_BOTH, postOnly=True,
                                     timeInForce=TimeInForce.GTT, expiryPeriod=expiry or self.expiry); n += 1; keep[side].append(k)

    def _rev_copy_step(self, book_id, tgt, at, mid, pr):
        """§1273: one step of the copy mode. pr = the model forecast if a signal check is due (else None). Returns (target units, signal time).
        §1286 REV_COPY_HOLD > 0: every burst is a leg that is taken out of the target REV_COPY_HOLD sim s after it was added (the model's horizon)."""
        if self.rev_copy_hold > 0 and tgt:
            lg = self._legs.setdefault(book_id, [])
            while lg and lg[0][0] <= self._sec - self.rev_copy_hold:
                _, u = lg.pop(0)
                tgt = tgt - u if (tgt > 0) == (u > 0) else tgt
                if (tgt > 0) != (u > 0) or abs(tgt) * mid < self.rev_usd / 4: tgt = 0.0
            if not lg: tgt = 0.0
        if tgt and self._sec - self._slice_at.get(book_id, -10 ** 9) >= self.rev_slice_cool and self._rev_take(book_id, tgt, mid):
            tgt = tgt * (1.0 - self.rev_slice); self._slice_at[book_id] = self._sec
            self._slice_n = getattr(self, "_slice_n", 0) + 1
            if abs(tgt) * mid < self.rev_usd / 2:
                tgt = 0.0
        if not tgt:
            self._rev_px.pop(book_id, None); self._legs.pop(book_id, None)
        if pr is not None and abs(pr) >= self._rf.th * self.rev_th_k and not (self.rev_skip_vol and int(book_id) < 63):
            sg = 1.0 if pr > 0 else -1.0
            if not tgt or (tgt > 0) == (sg > 0):
                add = min(self.rev_usd, self.rev_max_usd - abs(tgt) * mid) / mid
                if add * mid >= self.rev_usd / 2:
                    m0 = self._rev_px.get(book_id)
                    self._rev_px[book_id] = mid if not (m0 and tgt) else (m0 * abs(tgt) + mid * add) / (abs(tgt) + add)
                    tgt = tgt + sg * add; at = self._sec
                    if self.rev_copy_hold > 0: self._legs.setdefault(book_id, []).append((self._sec, sg * add))
                    self._model_n = getattr(self, "_model_n", 0) + 1
        return tgt, at

    def _rev_take(self, book_id, tgt, mid):
        """§1258: True when an open model position has reached its profit target."""
        m0 = self._rev_px.get(book_id)
        if not self.rev_tp_bp or not tgt or not m0:
            return False
        return (1.0 if tgt > 0 else -1.0) * (mid - m0) / m0 * 1e4 >= self.rev_tp_bp

    def _clock_check(self):
        """§1265: a sim-day reset sends the clock from ≈ 86,400 back to ≈ 0. Every "last time I did X" stamp then sat in the future, so checks like
        `now - last >= step` never passed again: x1 stopped entering AND exiting for 3.5 h on 11-07. Shift every stored stamp by the jump and clear
        per-second histories (they describe the old market). The pace ledger and bucket shift themselves (they keep the volume, §1255)."""
        prev = getattr(self, "_sec_prev", None); self._sec_prev = self._sec
        if prev is None or self._sec >= prev - 60:
            return
        d = self._sec - prev
        for name in ("_ioc_logged", "_mkq_logged", "_mk_logged", "_mkt_logged", "_qerr_at", "_rej_at", "_pace_logged", "_hb_at"):
            if isinstance(getattr(self, name, None), (int, float)):
                setattr(self, name, getattr(self, name) + d)
        for name in ("_last_take", "_sleeve_at", "_tilt_at", "_dbg_at", "_lock_at", "_slice_at"):
            dd = getattr(self, name, None)
            if isinstance(dd, dict):
                for k in list(dd): dd[k] = dd[k] + d
        for k, sides in getattr(self, "_pull_until", {}).items():
            for side in list(sides): sides[side] = sides[side] + d
        rv = getattr(self, "_rev", {})
        for k in list(rv): rv[k] = (rv[k][0], rv[k][1] + d)
        for k, lg in getattr(self, "_legs", {}).items():   # §1286 copy-hold legs
            lg[:] = [(t + d, u) for t, u in lg]
        for name in ("_mids", "_sflow", "_oflow", "_mid_hist", "_pending", "_mk_mid", "_bbo"):
            dd = getattr(self, name, None)
            if isinstance(dd, dict): dd.clear()
        bt.logging.warning(f"CLOCK RESET: sim time went back {-d} s; all stored times shifted, per-second histories cleared (decisions.md §1265)")

    def _tok_accrue(self, book_id, sec):
        st = self._tok.get(book_id)
        burst = self.pace_rate * self.pace_burst
        if st is None:
            st = self._tok[book_id] = [max(burst, self.pace_start), sec]
        dt = sec - st[1]
        if dt > 0:                                         # time never runs backwards here: a new simulation shifts the stored times instead
            if st[0] < burst:                              # refill only up to the normal burst; a larger starting balance is spent, never topped up
                st[0] = min(burst, st[0] + dt * self.pace_rate)
            st[1] = sec
        return st

    def _tok_spend(self, book_id, sec, value):
        self._tok_accrue(book_id, sec)[0] -= value

    def _pace_day(self, book_id):
        h = self._pace.get(book_id)
        if not h:
            return 0.0
        lo = self._sec - self.pace_period
        if h[0][0] <= lo:
            self._pace[book_id] = h = [x for x in h if x[0] > lo]
        return sum(v for _, v in h)

    def _pace_hold_ok(self, book_id):
        """§1317: may a paced-out book keep its deep resting orders? Calm books only, bucket above −MK_PACE_HOLD, 24-h ledger under pace_cap (hard backstop)."""
        return (self.mk_pace_hold > 0 and 63 <= int(book_id) < 102 and self._pace_day(book_id) < self.pace_cap
                and self._tok_accrue(book_id, self._sec)[0] > -self.mk_pace_hold)

    def _pace_hold_drop(self, book, orders, tick):
        """§1317: orders to pull on a soft-gated book: anything AT or INSIDE the others' best (the touch); orders ≥ 1 tick behind it stay resting."""
        ob, oa = self._others_best(book, orders)
        return [o for o in orders if (o.side == OrderDirection.BUY and (ob is None or o.price > ob - tick / 2))
                or (o.side == OrderDirection.SELL and (oa is None or o.price < oa + tick / 2))]

    def _paced_out(self, book_id):
        return self._tok_accrue(book_id, self._sec)[0] <= 0 or self._pace_day(book_id) >= self.pace_cap

    def _pace_sync(self):
        """§1255: pace_sync.py writes the validator's own per-book daily_volume next to the ledger. Where it exceeds what we counted (fills during a restart
        or a missed step), charge the difference once, in the ledger too, so nothing the validator counts is ever invisible to the bucket."""
        if not self.pace_ledger:
            return
        path = os.path.join(os.path.dirname(self.pace_ledger), f"pace_sync_{self.uid}.json")
        try:
            data = json.load(open(path))
        except Exception:
            return
        n = 0
        for bk, v in data.items():
            b = int(bk); gap = float(v) - self._pace_day(b)
            if gap > 1000.0:
                key = (b, f"sync{self._sec}", self._sec)
                if key in self._pace_seen:
                    continue
                self._pace_seen.add(key); self._pace[b].append((self._sec, gap)); self._tok_spend(b, self._sec, gap); n += 1
                try:
                    with open(self.pace_ledger, "a") as fh:
                        fh.write(json.dumps([b, self._sec, gap, key[1], self._sec]) + "\n")
                except Exception:
                    pass
        if n:
            bt.logging.warning(f"PACE SYNC: charged {n} books for volume the validator counted and our ledger had missed")

    def _pace_status(self):
        """One line per sim minute (§1255): a miner that stops trading for pacing, or nears the cap, must be visible, never silent."""
        self._pace_sync()
        books = sorted(self._pace)
        days = sorted(self._pace_day(b) for b in books) or [0.0]
        out = sum(1 for b in books if self._paced_out(b))
        worst = max(books, key=self._pace_day, default=None)
        vv = self._val_vol.get(worst) if worst is not None else None
        bt.logging.info(f"PACE STATUS: {out} of {len(books)} traded books blocked | 24h notional median ${days[len(days) // 2]:,.0f} max ${days[-1]:,.0f} of ${self.pace_cap:,.0f}"
                        f" | worst book {worst} ledger ${days[-1]:,.0f} validator traded_volume {vv}")

    def _toxic_update(self, book_id, book, sec, mid, tick):
        """Track our own maker fills on this book; 30 s later mark them against the mid and keep an EMA; pause the book when it is bad."""
        pend = self._pending.setdefault(book_id, [])
        for e in book.events or []:
            if getattr(e, "y", "") == "t" and e.Ma == self.uid:
                pend.append((e.timestamp // 1_000_000_000 + 30, 1 if e.side == 1 else -1, e.price))
        keep = []
        for due, side, price in pend:
            if due <= sec:
                mo = side * (mid - price) / tick
                self._mo[book_id] = 0.8 * self._mo.get(book_id, 0.0) + 0.2 * mo
            else:
                keep.append((due, side, price))
        self._pending[book_id] = keep
        if self._mo.get(book_id, 0.0) < -self.toxic:
            self._paused[book_id] = sec + self.toxic_pause
            self._mo[book_id] = 0.0                        # fresh start after the pause
        return self._paused.get(book_id, 0) > sec

    def _flow_signal(self, book_id, book):
        """Signed taker volume this update (side 0 = taker bought), smoothed; +1 = persistent buying pressure."""
        net = sum(e.quantity * (1 if e.side == 0 else -1) for e in (book.events or []) if getattr(e, "y", "") == "t")
        gross = sum(e.quantity for e in (book.events or []) if getattr(e, "y", "") == "t")
        d = self.flow_decay
        self._flow[book_id] = d * self._flow.get(book_id, 0.0) + (1 - d) * net
        self._absflow[book_id] = d * self._absflow.get(book_id, 0.0) + (1 - d) * gross
        return self._flow[book_id] / self._absflow[book_id] if self._absflow[book_id] > 0 else 0.0

    def _quote(self, response, book_id, book, acct):
        """arms (§1207): book n runs arm n mod (arms + 1); arm 0 = the configured params, arm k applies its overrides for this book only."""
        ov = self._arms[int(book_id) % len(self._arms)] if self._arms else None
        if not ov:
            return self._quote_inner(response, book_id, book, acct)
        saved = {k: getattr(self, k) for k in ov}
        try:
            for k, v in ov.items():
                setattr(self, k, v)
            return self._quote_inner(response, book_id, book, acct)
        finally:
            for k, v in saved.items():
                setattr(self, k, v)

    def _quote_inner(self, response, book_id, book, acct):
        if self.pace_cap:
            try:
                self._val_vol[int(book_id)] = acct.traded_volume
            except Exception:
                pass
        pd, vd = self.price_decimals(book_id), self.volume_decimals(book_id)
        tick = 10.0 ** -pd
        bid, ask = book.bids[0].price, book.asks[0].price
        qb, qa = book.bids[0].quantity, book.asks[0].quantity
        mid = (bid + ask) / 2
        spread = ask - bid
        micro = (bid * qa + ask * qb) / (qb + qa) if qb + qa > 0 else mid
        base0 = acct.base_balance.initial or 0.0
        quote0 = acct.quote_balance.initial or 0.0
        wealth0 = base0 * mid + quote0
        if wealth0 <= 0:
            return
        inv = (acct.base_balance.total - base0) * mid / wealth0
        tgt_units = 0.0
        if self.tilt_bp:
            f0 = getattr(book, "fundamental", None) or getattr(book, "f", None)
            if f0:
                if self._sec - self._tilt_at.get(book_id, -10 ** 9) >= self.sleeve_step:
                    u = (f0 - mid) / mid * 1e4; cur = self._tilt.get(book_id, 0.0)
                    self._tilt[book_id] = 1.0 if u > self.tilt_bp else (-1.0 if u < -self.tilt_bp else cur)
                    self._tilt_at[book_id] = self._sec
                tgt_units = self._tilt.get(book_id, 0.0) * self.tilt_notional / mid
                inv = (acct.base_balance.total - base0 - tgt_units) * mid / wealth0
        fair = mid + self.micro * (micro - mid) - self.skew * inv * spread
        fundamental = getattr(book, "fundamental", None) or getattr(book, "f", None)
        if self.fund and fundamental:
            fair += self._fund_shift(fundamental, mid, spread)
        if self.fund_mv:
            fair += self._fund_mv_shift(int(book_id), spread)
        if self.flow:
            fair += self.flow * spread * self._flow_signal(book_id, book)
        trend = 0.0
        pred = 0.0
        if self.model is not None:
            pred = self._predict(book_id, book, self._sec, mid)
            fair += self.alpha_k * pred
            mids = self._mids.get(book_id, {})
            if self.trend_z and self._sec - 120 in mids:
                i = self.model["names"].index("ret120")
                trend = (mid - mids[self._sec - 120] - self.model["mu"][i]) / self.model["sd"][i]
        inside = spread > 2.5 * tick and not self.join
        bid_px = min(bid + tick if inside else bid, fair - self.edge * tick, ask - tick)
        ask_px = max(ask - tick if inside else ask, fair + self.edge * tick, bid + tick)
        if self.back:
            bid_px = min(bid_px, bid - self.back * tick)
            ask_px = max(ask_px, ask + self.back * tick)
        bid_px = round(round(bid_px / tick) * tick, pd)
        ask_px = round(round(ask_px / tick) * tick, pd)
        if self.snap:                                      # quote only at prices other makers already hold (§1207): 54% of our fills came alone at a
            ours = defaultdict(float)                      # price nobody else quoted, at −3.87 ticks; sharing a level ≈ break-even
            for o in acct.orders:
                ours[(int(o.side), o.price)] += o.quantity or 0.0
            held = lambda side, lv: lv.quantity - ours.get((side, lv.price), 0.0) > 1e-9
            bid_px = max((l.price for l in book.bids if l.price <= bid_px + tick / 2 and held(0, l)), default=None)
            ask_px = min((l.price for l in book.asks if l.price >= ask_px - tick / 2 and held(1, l)), default=None)
        sz = self.mk_vol_size if (self.mk_vol_size > 0 and int(book_id) < 63) else self.size   # §1275: own size on the $300 books (long-lived fleet quotes ≈ $3k there)
        if self.mk_dec_size > 0 and int(book_id) >= 102: sz = self.mk_dec_size   # §1313: fleet 4-dec order size
        qty = round(max(sz * wealth0 / mid, self.min_order_size(book_id)), vd)
        want = {}
        if int(book_id) in self.skip:
            self._cancel_all(response, book_id, acct.orders)   # skipped book: pull our quotes and stay out (§1293: one instruction)
            if self.lock_dir and len(self.skip) < 128:     # §1289 a MAKER on a book it does not quote (book split between our makers): still clear our
                for side in (OrderDirection.BUY, OrderDirection.SELL):   # taker's locks, or x1 would wait on every book some maker skips
                    lk, ak = f"{self.lock_dir}/lock_{book_id}_{int(side)}", f"{self.lock_dir}/ack_{book_id}_{int(side)}_{self.uid}"
                    if os.path.exists(lk):
                        if not any(o.side == side for o in acct.orders):   # ack only once nothing of ours rests on that side
                            with open(ak + ".tmp", "w") as fh:
                                fh.write(str(self._sec))
                            os.replace(ak + ".tmp", ak)
                    elif os.path.exists(ak):
                        os.remove(ak)
                return                                     # a maker never trades the books it skips
            if self.sleeve_books is not None and int(book_id) not in self.sleeve_books:
                return                                     # sleeve_file set: trade only the sleeve books (another UID of ours quotes the rest)
            units = acct.base_balance.total - base0
            target, cool = 0.0, self.take_cool
            if self._rf is not None and (self.sleeve_books is None or int(book_id) in self.sleeve_books):
                trades, of = [], 0.0                            # §1233: feed this step's events, then trade the forecast's sign when it is strong
                for e in book.events or []:
                    kind = getattr(e, "y", "")
                    if kind == "t":
                        trades.append(((e.timestamp // 1_000_000_000) if e.timestamp else self._sec, e.price, e.quantity, getattr(e, "Ta", None)))
                    elif kind == "o" and getattr(e, "price", None) is not None:
                        of += (e.quantity or 0.0) if e.side == 0 else -(e.quantity or 0.0)
                    elif kind == "c" and getattr(e, "side", None) is not None:
                        of -= (e.quantity or 0.0) if e.side == 0 else -(e.quantity or 0.0)
                bd = sum(l.quantity or 0.0 for l in (book.bids or [])[:5]); ad = sum(l.quantity or 0.0 for l in (book.asks or [])[:5])
                self._rf.update(int(book_id), self._sec, mid, fundamental, (bd - ad) / (bd + ad) if bd + ad else 0.0, (ask - bid) / mid * 1e4,
                                trades, of, own_uid=self.uid)
                tgt, at = self._rev.get(book_id, (0.0, -10 ** 9))
                if self.rev_copy:
                    pr = self._rf.predict(int(book_id), self._sec) if self._sec - at >= self.sleeve_step else None
                    tgt, at = self._rev_copy_step(book_id, tgt, at, mid, pr)
                else:
                    if self._sec - at >= self.rev_hold:
                        tgt = 0.0
                    if self._rev_take(book_id, tgt, mid):
                        tgt = 0.0
                    if not tgt:
                        self._rev_n.pop(book_id, None)
                    elif self.rev_legs > 1:
                        tgt = self._rev_leg(book_id, tgt, mid)
                    if self._sec - at >= self.sleeve_step and not (self.rev_tp_bp and tgt):
                        pr = self._rf.predict(int(book_id), self._sec)
                        if pr is not None and abs(pr) >= self._rf.th * self.rev_th_k and not (self.rev_skip_vol and int(book_id) < 63):
                            sg = 1.0 if pr > 0 else -1.0
                            if self.rev_rand == 1: sg = self._rev_rng.choice((1.0, -1.0))
                            elif self.rev_rand == 2: sg = -sg
                            tgt, at = sg * self.rev_usd / mid, self._sec
                            self._rev_px[book_id] = mid
                            self._rev_n[book_id] = 1; self._rev_last[book_id] = mid
                            self._model_n = getattr(self, "_model_n", 0) + 1
                self._rev[book_id] = (tgt, at)
                target, cool = tgt, self.sleeve_cool
            elif self.rev_look > 0 and (self.sleeve_books is None or int(book_id) in self.sleeve_books):
                h = self._mid_hist.setdefault(book_id, [])
                h.append((self._sec, mid))
                while len(h) > 1 and h[1][0] <= self._sec - self.rev_look:
                    h.pop(0)                               # h[0] = the newest sample at least REV_LOOK old
                tgt, at = self._rev.get(book_id, (0.0, -10 ** 9))
                if self._sec - at >= self.rev_hold:
                    tgt = 0.0
                if h[0][0] <= self._sec - self.rev_look and self._sec - at >= self.sleeve_step:
                    r = (mid - h[0][1]) / h[0][1] * 1e4
                    d = -1.0 if r > 0 else 1.0
                    if abs(r) >= self.sleeve_bp and (self.rev_imb <= -1.0 or d * self._depth_imb(book) >= self.rev_imb):
                        if self.rev_rand == 1: d = self._rev_rng.choice((1.0, -1.0))   # §1247 lab: same timing and size, random / opposite direction
                        elif self.rev_rand == 2: d = -d
                        tgt, at = d * self.rev_usd / mid, self._sec
                self._rev[book_id] = (tgt, at)
                target, cool = tgt, self.sleeve_cool
            elif self.sleeve_bp and fundamental and (self.sleeve_books is None or int(book_id) in self.sleeve_books):
                if self._sec - self._sleeve_at.get(book_id, -10 ** 9) >= self.sleeve_step:
                    u = (fundamental - mid) / mid * 1e4; cur = self._sleeve.get(book_id, 0.0)
                    if self.sleeve_dm > 0:
                        e = self._gap_ema.get(book_id, u); e = e + (1 - 0.5 ** (self.sleeve_step / self.sleeve_dm)) * (u - e)
                        self._gap_ema[book_id] = e; u = u - e
                    u = u * self.sleeve_sign
                    if self.sleeve_prop > 0:
                        tgt = self.sleeve_q * max(-1.0, min(1.0, u / self.sleeve_prop))
                        self._sleeve[book_id] = tgt if abs(tgt - cur) >= self.sleeve_band * self.sleeve_q else cur
                    else:
                        self._sleeve[book_id] = self.sleeve_q if u > self.sleeve_bp else (-self.sleeve_q if u < -self.sleeve_bp else cur)
                    self._sleeve_at[book_id] = self._sec
                target, cool = self._sleeve.get(book_id, 0.0), self.sleeve_cool
            gap = target - units
            if self.lock_dir and abs(gap) < self.min_order_size(book_id):
                self._lock_release(book_id)
            if self.skip_flat and abs(gap) >= self.min_order_size(book_id) and self._sec - self._last_take.get(book_id, -10 ** 9) >= cool:
                side = OrderDirection.BUY if gap > 0 else OrderDirection.SELL
                if self.pace_cap and abs(target) > abs(units) and self._paced_out(int(book_id)):
                    return                                 # §1245: over the volume pace on this book — no new exposure; exits still go
                if self.lock_dir and not self._lock_ok(book_id, OrderDirection.SELL if side == OrderDirection.BUY else OrderDirection.BUY):
                    return                                 # waiting for the maker UID to clear that side of the book
                px = bid if side == OrderDirection.SELL else ask
                q = round(min(abs(gap), self.take_size, qb if side == OrderDirection.SELL else qa, self.rev_clip_usd / px if self.rev_clip_usd else 1e18), vd)
                funded = (acct.base_balance.free >= q) if side == OrderDirection.SELL else (acct.quote_balance.free >= q * px)
                if q >= self.min_order_size(book_id) and funded:
                    response.limit_order(book_id=book_id, direction=side, quantity=q, price=px, stp=STP.CANCEL_OLDEST, postOnly=False,
                                         timeInForce=TimeInForce.IOC)
                    self._last_take[book_id] = self._sec
                    self._ioc_n = getattr(self, "_ioc_n", 0) + 1; self._ioc_usd = getattr(self, "_ioc_usd", 0.0) + q * px
            return
        if self._rf is not None and self.mk_model:              # §1238: feed the predictor on EVERY book each step (before paced/toxic returns)
            trades, of = [], 0.0
            for e in book.events or []:
                kind = getattr(e, "y", "")
                if kind == "t":
                    trades.append(((e.timestamp // 1_000_000_000) if e.timestamp else self._sec, e.price, e.quantity, getattr(e, "Ta", None)))
                elif kind == "o" and getattr(e, "price", None) is not None:
                    of += (e.quantity or 0.0) if e.side == 0 else -(e.quantity or 0.0)
                elif kind == "c" and getattr(e, "side", None) is not None:
                    of -= (e.quantity or 0.0) if e.side == 0 else -(e.quantity or 0.0)
            bd5 = sum(l.quantity or 0.0 for l in (book.bids or [])[:5]); ad5 = sum(l.quantity or 0.0 for l in (book.asks or [])[:5])
            fnd = getattr(book, "fundamental", None) or getattr(book, "f", None)
            self._rf.update(int(book_id), self._sec, mid, fnd, (bd5 - ad5) / (bd5 + ad5) if bd5 + ad5 else 0.0, (ask - bid) / mid * 1e4,
                            trades, of, own_uid=self.uid)
        if self.mk_nochase_bp > 0:
            self._bbo_rec(int(book_id), bid, ask)           # §1326: history for EVERY book every round, before the pace gate
        if self.fund_mv:
            self._fund_rec(int(book_id), getattr(book, "fundamental", None) or getattr(book, "f", None))   # §1379: every book, every round
        if self.lock_dir:                                  # maker side of the handshake, FIRST (paced-out / toxic books return early below)
            for side in (OrderDirection.BUY, OrderDirection.SELL):
                lk, ak = f"{self.lock_dir}/lock_{book_id}_{int(side)}", f"{self.lock_dir}/ack_{book_id}_{int(side)}_{self.uid}"
                if os.path.exists(lk):
                    mine = [o for o in acct.orders if o.side == side]
                    self._cancel_all(response, book_id, mine)     # pull our quotes on the locked side now (§1293: one instruction)
                    if not mine:
                        with open(ak + ".tmp", "w") as fh:
                            fh.write(str(self._sec))
                        os.replace(ak + ".tmp", ak)
                elif os.path.exists(ak):
                    os.remove(ak)
        if self.pace_cap and self._paced_out(int(book_id)):
            if self._pace_hold_ok(int(book_id)):           # §1317 soft gate (calm): deep orders stay resting, touch / inside orders go, nothing new
                self._cancel_all(response, book_id, self._pace_hold_drop(book, acct.orders, tick))
                return
            self._cancel_all(response, book_id, acct.orders)   # over the volume pace on this book: pull our quotes and wait (§1293)
            return
        if self.toxic and self._toxic_update(book_id, book, self._sec, mid, tick):
            self._cancel_all(response, book_id, acct.orders)   # book paused: pull our quotes and stay out (§1293)
            return
        units = acct.base_balance.total - base0 - tgt_units
        if self.max_units and units >= self.max_units:
            inv = max(inv, self.max_inv)                   # at the long cap: no more bids
        if self.max_units and units <= -self.max_units:
            inv = min(inv, -self.max_inv)                  # at the short cap: no more offers
        if self.mk_calm_hs > 0 and 63 <= int(book_id) < 102:   # §1295 calm books: rest MK_CALM_HS half-spreads from the mid like the long-lived fleet (1.67)
            bid_px, ask_px = self._calm_px(bid, ask, tick, pd, bid_px, ask_px)
        sq = {}                                           # per-side quantity (fit_qty: the affordable part of qty, §1211 add. 21)
        if bid_px is not None and inv < self.max_inv:
            room = (acct.quote_balance.free + self._reserved(acct, OrderDirection.BUY)) / bid_px
            q = qty if room >= qty else (round(room * 0.98, vd) if self.fit_qty else 0.0)
            if q >= self.min_order_size(book_id) and q > 0:
                want[OrderDirection.BUY] = bid_px; sq[OrderDirection.BUY] = q
        if ask_px is not None and inv > -self.max_inv:
            room = acct.base_balance.free + self._reserved(acct, OrderDirection.SELL)
            q = qty if room >= qty else (round(room * 0.98, vd) if self.fit_qty else 0.0)
            if q >= self.min_order_size(book_id) and q > 0:
                want[OrderDirection.SELL] = ask_px; sq[OrderDirection.SELL] = q
        if self.dbg and self._sec - self._dbg_at.get(book_id, -10 ** 9) >= 60:
            self._dbg_at[book_id] = self._sec
            bt.logging.info(f"DBG book {book_id} mid {mid:.4f} units {units:.1f} inv {inv:+.3f} qty {qty} qfree {acct.quote_balance.free:.1f} "
                            f"bfree {acct.base_balance.free:.1f} base0 {base0:.1f} wealth0 {wealth0:.0f} bid_px {bid_px} ask_px {ask_px} want {sorted(int(k) for k in want)} pred {pred:+.2f} open {len(acct.orders)} {[(int(o.side), o.price, round(o.quantity or 0, 1)) for o in acct.orders][:4]}")
        if self.take and abs(pred) > self.take * tick and self._sec - self._last_take.get(book_id, -10 ** 9) >= self.take_cool:
            side = OrderDirection.BUY if pred > 0 else OrderDirection.SELL
            room = (self.max_units - units if side == OrderDirection.BUY else self.max_units + units) if self.max_units else self.take_size
            q = round(min(self.take_size, qa if side == OrderDirection.BUY else qb, max(room, 0.0)), vd)
            px = ask if side == OrderDirection.BUY else bid
            funded = (acct.quote_balance.free >= q * px) if side == OrderDirection.BUY else (acct.base_balance.free >= q)
            if q >= self.min_order_size(book_id) and funded:
                response.limit_order(book_id=book_id, direction=side, quantity=q, price=px, stp=STP.CANCEL_OLDEST, postOnly=False,
                                     timeInForce=TimeInForce.IOC)
                self._last_take[book_id] = self._sec
                want.pop(OrderDirection.SELL if side == OrderDirection.BUY else OrderDirection.BUY, None)   # never rest on the side we take
        if self.mk_skip_vol and int(book_id) < 63:
            want.clear()
        if self.mk_trend_bp > 0:
            h = self._mk_mid.setdefault(book_id, [])
            h.append((self._sec, mid))
            while len(h) > 1 and h[1][0] <= self._sec - self.mk_trend_win:
                h.pop(0)                                   # h[0] = the newest sample at least MK_TREND_WIN old
            self._mkt_n[0] += 1
            if h[0][0] <= self._sec - self.mk_trend_win:
                mv = (mid - h[0][1]) / h[0][1] * 1e4
                if mv >= self.mk_trend_bp and want.pop(OrderDirection.SELL, None) is not None:
                    self._mkt_n[1] += 1
                elif mv <= -self.mk_trend_bp and want.pop(OrderDirection.BUY, None) is not None:
                    self._mkt_n[1] += 1
            if self._sec - getattr(self, "_mkt_logged", -10 ** 9) >= 60:
                self._mkt_logged = self._sec
                bt.logging.info(f"MK TREND: {self._mkt_n[1]} sides pulled of {self._mkt_n[0]} decisions")
        if self.mk_min_spread_bp > 0 or self.mk_thin_ratio > 0:   # §1242 quote-quality rules (x3 fill study)
            self._mkq_n[0] += 1
            if self.mk_min_spread_bp > 0 and (ask - bid) / mid * 1e4 < self.mk_min_spread_bp:
                want.clear(); self._mkq_n[1] += 1                # tight book: our fills here keep < 0% of the spread
            elif self.mk_thin_ratio > 0 and qb and qa and not (self.mk_thin_vol_off and int(book_id) < 63) and not (self.mk_thin_only_vol and int(book_id) >= 63):   # §1301: thin rule on the $300 books only   # §1276: off on the $300 books (fleet quotes two-sided there)
                if qb < self.mk_thin_ratio * qa and want.pop(OrderDirection.BUY, None) is not None:
                    self._mkq_n[2] += 1                          # thin bid queue vs the ask: the bid gets run over
                if qa < self.mk_thin_ratio * qb and want.pop(OrderDirection.SELL, None) is not None:
                    self._mkq_n[2] += 1
            if self._sec - getattr(self, "_mkq_logged", -10 ** 9) >= 60:
                self._mkq_logged = self._sec
                bt.logging.info(f"MK QUALITY: {self._mkq_n[0]} decisions, {self._mkq_n[1]} skipped tight, {self._mkq_n[2]} thin sides pulled")
        if self._rf is not None and self.mk_model:              # §1238 guard (features fed at the top of the making path)
            if self.mk_pull_bp > 0:
                fc = self._rf.predict(int(book_id), self._sec); self._mk_n[1] += 1
                if fc is not None and fc >= self.mk_pull_bp and want.pop(OrderDirection.SELL, None) is not None:
                    self._mk_n[0] += 1                         # model expects the price to rise: an offer here gets lifted and loses
                elif fc is not None and fc <= -self.mk_pull_bp and want.pop(OrderDirection.BUY, None) is not None:
                    self._mk_n[0] += 1
                if self._sec - getattr(self, "_mk_logged", -10 ** 9) >= 60:
                    self._mk_logged = self._sec
                    bt.logging.info(f"MK GUARD: pulled {self._mk_n[0]} quote sides of {self._mk_n[1]} decisions")
        if self.pull and pred > self.pull * tick:
            want.pop(OrderDirection.SELL, None)            # price about to rise: do not leave an offer for a sniper to lift
        elif self.pull and pred < -self.pull * tick:
            want.pop(OrderDirection.BUY, None)             # price about to fall: do not leave a bid to be hit
        near = self._near.get(book_id, 0.0); until = self._pull_until.setdefault(book_id, {})
        fp_on = self.flow_pull and not (self.flow_pull_vol_only and int(book_id) >= 63)
        if fp_on and near > self.flow_pull:
            until[OrderDirection.SELL] = self._sec + self.flow_cool   # new orders crowding the bid near the touch: our offer gets lifted
        elif fp_on and near < -self.flow_pull:
            until[OrderDirection.BUY] = self._sec + self.flow_cool
        for side, t in until.items():
            if self._sec <= t:
                want.pop(side, None)
        if self.mk_tflow_usd > 0 and int(book_id) < 63:   # §1308 trade-flow pull ($300 books): x2's worst fills (44% of $, kept÷edge 0.25) came while trades hit the OTHER side
            tf = self._tflow_usd(book_id, mid)            # + = takers buying (hitting the asks) over the last MK_TFLOW_WIN sim s
            if tf > self.mk_tflow_usd and want.pop(OrderDirection.BUY, None) is not None:
                self._tf_n = getattr(self, "_tf_n", 0) + 1
            elif tf < -self.mk_tflow_usd and want.pop(OrderDirection.SELL, None) is not None:
                self._tf_n = getattr(self, "_tf_n", 0) + 1
        if self.trend_z and abs(trend) > self.trend_z and trend * inv < 0:
            want.pop(OrderDirection.BUY if inv > 0 else OrderDirection.SELL, None)   # long into a fall / short into a rise: unwind only
        if self.lock_dir:
            for side in (OrderDirection.BUY, OrderDirection.SELL):
                if os.path.exists(f"{self.lock_dir}/lock_{book_id}_{int(side)}"):
                    want.pop(side, None)                   # a taker UID of ours is about to trade into this side: stay off it (ack handled above)
        # the validator adds 5-25 ms to every instruction after a book's first: cancel the side the prediction says is exposed first
        orders = sorted(acct.orders, key=lambda o: (o.side == OrderDirection.SELL) != (pred > 0)) if self.cancel_first else acct.orders
        extra = {}
        if self.mk_lad1 > 0 or self.mk_lad2 > 0:           # §1252 ladder: only on sides still wanted, so every pull above (lock handshake included) removes it
            for side in want:
                lv = {}
                for k in (self.mk_lad1, self.mk_lad2):
                    if k > 0:
                        n = (mid - k * (ask - bid)) / tick if side == OrderDirection.BUY else (mid + k * (ask - bid)) / tick
                        p = round(math.floor(n + 1e-9) * tick if side == OrderDirection.BUY else math.ceil(n - 1e-9) * tick, pd)
                        if p != want[side] and p > 0: lv[p] = sq.get(side, qty)
                extra[side] = lv
        if self.mk_nochase_bp > 0 and want:                # §1323 no-chase (all quoted books)
            self._nc_n = getattr(self, "_nc_n", 0) + self._nochase(int(book_id), want, bid, ask, mid, pd)
        if self.mk_dec_size > 0 and int(book_id) >= 102:  # §1313 4-dec books, long-lived fleet pattern: just ahead of the others' best + one deep order
            k = self._dec_targets(book, acct.orders, want, tick, pd)
            if k:
                self._vol_ladder(response, book_id, orders, want, sq, qty, qty, tick, pd, levels=[k], tol=max(1, k // 2))
            else:
                self._cancel_all(response, book_id, acct.orders)   # §1332: spread too tight for the fleet pattern: pull all with ONE instruction
            return
        if self.mk_vol_lad and int(book_id) < 63:          # §1278 $300-book ladder (long-lived fleet), §1279: resting ladder + the validator's per-book instruction limit
            vq = round(max(self.mk_vol_lad_size * wealth0 / mid, self.min_order_size(book_id)), vd)
            if self.mk_vol_lazy:
                self._vol_lazy(response, book_id, orders, want, vq, tick, pd)
            else:
                ob_v = self._others_best(book, acct.orders) if (self.mk_vol_inside or self.mk_vol_touch_min) else None
            nt_v = bool(self.mk_vol_touch_min and ob_v and ob_v[0] is not None and ob_v[1] is not None and round((ob_v[1] - ob_v[0]) / tick) < self.mk_vol_touch_min)
            self._vol_ladder(response, book_id, orders, want, sq, qty, vq, tick, pd, inside=0 if nt_v else self.mk_vol_inside,
                                 obest=ob_v if self.mk_vol_inside else None, no_touch=nt_v)
            return
        if self.mk_calm_lad and 63 <= int(book_id) < 102:  # §1303 calm-book ladder: the fleet's calm volume is 60% from orders resting 1+ ticks behind the touch
            vq = round(max(self.mk_calm_lad_size * wealth0 / mid, self.min_order_size(book_id)), vd)
            ob_ = self._others_best(book, acct.orders) if (self.mk_calm_hold or self.mk_calm_touch_min) else None
            nt = bool(self.mk_calm_touch_min and ob_ and ob_[0] is not None and ob_[1] is not None and round((ob_[1] - ob_[0]) / tick) < self.mk_calm_touch_min)
            self._vol_ladder(response, book_id, orders, want, sq, qty, vq, tick, pd, levels=self.mk_calm_lad, expiry=self.mk_calm_expiry or None,
                             hold=self.mk_calm_hold, obest=ob_ if self.mk_calm_hold else None, no_touch=nt)
            return
        for o in orders:
            if o.price in extra.get(o.side, {}):
                extra[o.side].pop(o.price); continue       # ladder level already resting: keep its queue place
            px = want.get(o.side)
            behind = None if px is None else round(((px - o.price) if o.side == OrderDirection.BUY else (o.price - px)) / tick, 6)
            if px == o.price or (self.sticky and behind is not None and 0 <= behind <= self.sticky):
                want.pop(o.side)                      # at the target, or up to STICKY ticks less aggressive: keep its queue place (§1207)
            else:
                response.cancel_order(book_id, o.id)
        for side, px in want.items():
            response.limit_order(book_id=book_id, direction=side, quantity=sq.get(side, qty), price=px, stp=STP.CANCEL_BOTH, postOnly=True,
                                 timeInForce=TimeInForce.GTT, expiryPeriod=self.expiry)
        for side, lv in extra.items():
            for p in sorted(lv):
                response.limit_order(book_id=book_id, direction=side, quantity=lv[p], price=p, stp=STP.CANCEL_BOTH, postOnly=True,
                                     timeInForce=TimeInForce.GTT, expiryPeriod=self.expiry)

    def _record(self, state):
        ts = state.timestamp
        for book_id, book in (self._books if self._books is not None else state.books or {}).items():
            for e in book.events or []:
                if getattr(e, "y", "") == "t":
                    self.tape.write(json.dumps({"ts": e.timestamp, "book": book_id, "id": e.id, "p": e.price, "q": e.quantity, "s": e.side,
                                                "Ma": e.Ma, "Ta": e.Ta, "Mf": e.Mf, "Tf": e.Tf, "Mi": getattr(e, "Mi", None)}) + "\n")
            if book.bids and book.asks:
                b0, a0 = book.bids[0].price, book.asks[0].price
                tick = 10.0 ** -self.price_decimals(book_id)
                of = {"nb": 0.0, "na": 0.0, "nb2": 0.0, "na2": 0.0, "cb": 0.0, "ca": 0.0}   # new / near-touch (<= 2 ticks) / cancelled size
                for e in book.events or []:
                    kind = getattr(e, "y", "")
                    if kind == "o" and e.price is not None:
                        side = "b" if e.side == 0 else "a"
                        of["n" + side] += e.quantity
                        if (side == "b" and e.price >= b0 - 2 * tick) or (side == "a" and e.price <= a0 + 2 * tick):
                            of["n" + side + "2"] += e.quantity
                    elif kind == "c" and getattr(e, "side", None) is not None:   # pydantic Cancellation has no side (x2 crash 11-05)
                        of["c" + ("b" if e.side == 0 else "a")] += getattr(e, "quantity", 0.0) or 0.0
                self.tape.write(json.dumps({"ts": ts, "book": book_id, "of": {k: round(v, 4) for k, v in of.items()}}) + "\n")
                self.tape.write(json.dumps({"ts": ts, "book": book_id, "bid": book.bids[0].price, "ask": book.asks[0].price,
                                            "bids": [[l.price, l.quantity] for l in book.bids[:5]], "asks": [[l.price, l.quantity] for l in book.asks[:5]],
                                            "fund": getattr(book, "fundamental", None) or getattr(book, "f", None)}) + "\n")
            acct = self.accounts.get(book_id) if self.qlog else None
            if acct is not None and getattr(book, "raw_b", None) is not None:   # qlog=1 (raw mode): where each of our orders sits in its queue
                q = []
                for o in acct.orders:
                    for lv in (book.raw_b if o.side == OrderDirection.BUY else book.raw_a):
                        if lv["p"] == o.price:
                            ahead = 0.0
                            for x in lv.get("o") or []:
                                if x.get("i") == o.id:
                                    break
                                ahead += x.get("q") or 0.0
                            q.append([int(o.side), o.price, round(ahead, 4), round(lv["q"], 4), o.id])
                            break
                if q:
                    self.tape.write(json.dumps({"ts": ts, "book": book_id, "queue": q}) + "\n")
        self.tape.flush()

    @staticmethod
    def _depth_imb(book):
        """(bid depth − ask depth) / total over the top 5 levels: > 0 means more resting buyers (§1230)."""
        bd = sum(l.quantity or 0.0 for l in (book.bids or [])[:5]); ad = sum(l.quantity or 0.0 for l in (book.asks or [])[:5])
        return (bd - ad) / (bd + ad) if bd + ad > 0 else 0.0

    def _live_makers(self):
        """UIDs of our makers whose heartbeat is within LOCK_HB_S sim seconds (§1240); re-read at most once per sim second."""
        if getattr(self, "_lm_at", None) == self._sec:
            return self._lm
        out = []
        for f in os.listdir(self.lock_dir):
            if f.startswith("maker_") and f.endswith(".hb") and f[6:-3] != str(self.uid):   # never wait on ourselves
                try:
                    p = f"{self.lock_dir}/{f}"; age = self._sec - float(open(p).read())
                    if 0 <= age <= self.lock_hb_s and time.time() - os.path.getmtime(p) < 120:   # §1267: a dead maker's file (or one from before a sim reset) must not count as alive
                        out.append(f[6:-3])
                except (OSError, ValueError):
                    pass
        self._lm, self._lm_at = out, self._sec
        return out

    def _lock_ok(self, book_id, maker_side):
        """Taker half of the handshake: request the lock, and report whether EVERY live maker of ours has acknowledged it (no orders there).
        No live maker (all heartbeats stale) → no handshake needed: trade at once (§1240)."""
        makers = self._live_makers()
        if not makers:
            self._lock_release(book_id)
            return True
        lk = f"{self.lock_dir}/lock_{book_id}_{int(maker_side)}"
        key = (book_id, int(maker_side))
        if key not in self._lock_at or not os.path.exists(lk):
            with open(lk + ".tmp", "w") as fh:
                fh.write(str(self._sec))
            os.replace(lk + ".tmp", lk); self._lock_at[key] = self._sec
            return False
        if self._sec - self._lock_at[key] > self.lock_max:
            self._lock_release(book_id)                    # maker never cleared: give the side back, try again later
            return False
        try:
            return all(float(open(f"{self.lock_dir}/ack_{book_id}_{int(maker_side)}_{u}").read()) >= self._lock_at[key] for u in makers)
        except (OSError, ValueError):
            return False

    def _lock_release(self, book_id):
        for side in (OrderDirection.BUY, OrderDirection.SELL):
            self._lock_at.pop((book_id, int(side)), None)
            try:
                os.remove(f"{self.lock_dir}/lock_{book_id}_{int(side)}")
            except OSError:
                pass

    @staticmethod
    def _reserved(acct, side):
        """Funds our own resting orders on this side hold; they come back when we cancel and replace."""
        if side == OrderDirection.BUY:
            return sum(o.quantity * (o.price or 0.0) for o in acct.orders if o.side == OrderDirection.BUY)
        return sum(o.quantity for o in acct.orders if o.side == OrderDirection.SELL)


if __name__ == "__main__":
    launch(QuoteAgent)
