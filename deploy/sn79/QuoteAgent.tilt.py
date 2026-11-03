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


class _RawBook:
    __slots__ = ("bids", "asks", "events", "fundamental", "raw_b", "raw_a")

    def __init__(self, d):
        self.raw_b, self.raw_a = d.get("b") or [], d.get("a") or []    # levels with their resting orders in queue order (qlog)
        self.bids = [_Lv(x) for x in d.get("b") or []]
        self.asks = [_Lv(x) for x in d.get("a") or []]
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
        self.pace_win = int(getattr(c, "pace_win", 5400)); self.pace_k = float(getattr(c, "pace_k", 1.0))
        self._pace, self._pace_seen = defaultdict(list), set()
        if self.pace_cap and getattr(c, "tape", ""):
            try:
                rows = []
                for line in open(str(c.tape)):
                    if '"p":' in line and str(self.uid) in line:
                        r = json.loads(line)
                        if r.get("Ma") == self.uid or r.get("Ta") == self.uid:
                            rows.append((r["ts"] // 1_000_000_000, r["book"], r["p"] * r["q"], (r["book"], r.get("id"), r["ts"])))
                end = max((x[0] for x in rows), default=0)
                for sec, bk, v, key in rows:
                    if sec > end - self.pace_period and key not in self._pace_seen:
                        self._pace_seen.add(key); self._pace[bk].append((sec, v))
                bt.logging.info(f"PACE seeded {sum(len(v) for v in self._pace.values())} own fills on {len(self._pace)} books from the tape")
            except Exception as e:
                bt.logging.warning(f"PACE seed failed: {e}")
        self.dbg = int(getattr(c, "dbg", 0)); self._dbg_at = {}   # 1: log per quoted book once a minute (inventory, balances, wanted sides)      # 1: quote the affordable part of the order instead of skipping the side (§1211 add. 21)
        self.sleeve_bp = float(getattr(c, "sleeve_bp", 0.0))   # >0 (with skip_flat): on skipped books steer the position to ±SLEEVE_Q by the sign of
        self.sleeve_q = float(getattr(c, "sleeve_q", 10.0))     # (fundamental − mid)/mid beyond ±SLEEVE_BP (hysteresis), checked every SLEEVE_STEP
        self.sleeve_step = int(getattr(c, "sleeve_step", 10))   # sim s, one IOC per SLEEVE_COOL s: de-beta skill counts held inventory × Δmid
        self.sleeve_cool = int(getattr(c, "sleeve_cool", 5))    # and its 2.3 bp hurdle is per own notional (§1211 add. 20)
        self._sleeve, self._sleeve_at = {}, {}
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
        if self.own_ex:                                    # ids of our resting orders in this and the last 2 states: an order we placed rests
            self._own_hist.append({o.id for a in self.accounts.values() for o in (a.orders or [])})   # at least one state before its cancel
            self._own_hist = self._own_hist[-3:]; self._own = set().union(*self._own_hist)
            if self._sec % 60 == 0 and self.own_stats[1]:
                n, t, q, qt = self.own_stats
                bt.logging.info(f"OWN FLOW: our share of order/cancel events {n / t:.1%} by count, {q / max(qt, 1e-9):.1%} by size")
        if self.tape is not None:
            self._record(state)
        if self.pace_cap:
            for book_id, book in (self._books if self._books is not None else state.books or {}).items():
                for e in book.events or []:
                    if getattr(e, "y", "") == "t" and (e.Ma == self.uid or e.Ta == self.uid):
                        key = (int(book_id), e.id, e.timestamp)
                        if key not in self._pace_seen:
                            self._pace_seen.add(key); self._pace[int(book_id)].append((e.timestamp // 1_000_000_000, e.price * e.quantity))
        for book_id, book in (self._books if self._books is not None else state.books or {}).items():
            acct = self.accounts.get(book_id)
            if acct is None or not book.bids or not book.asks:
                continue
            try:
                self._quote(response, book_id, book, acct)
            except Exception:
                continue
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
            elif kind == "c" and e.side is not None:
                row[4 if e.side == 0 else 5] += e.quantity or 0.0
        for d, keep in ((mids, 125), (fl, 6), (ofl, max(6, self.flow_win + 1))):
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

    def _paced_out(self, book_id):
        h = self._pace.get(book_id)
        if not h:
            return False
        lo = self._sec - self.pace_period
        if h[0][0] <= lo:
            self._pace[book_id] = h = [x for x in h if x[0] > lo]
        day = sum(v for _, v in h); recent = sum(v for t, v in h if t > self._sec - self.pace_win)
        return day >= self.pace_cap or recent >= self.pace_cap * self.pace_win / self.pace_period * self.pace_k

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
            fair += self.fund * (fundamental - mid)
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
        qty = round(max(self.size * wealth0 / mid, self.min_order_size(book_id)), vd)
        want = {}
        if int(book_id) in self.skip:
            for o in acct.orders:                          # skipped book: pull our quotes and stay out
                response.cancel_order(book_id, o.id)
            if self.sleeve_books is not None and int(book_id) not in self.sleeve_books:
                return                                     # sleeve_file set: trade only the sleeve books (another UID of ours quotes the rest)
            units = acct.base_balance.total - base0
            target, cool = 0.0, self.take_cool
            if self.sleeve_bp and fundamental and (self.sleeve_books is None or int(book_id) in self.sleeve_books):
                if self._sec - self._sleeve_at.get(book_id, -10 ** 9) >= self.sleeve_step:
                    u = (fundamental - mid) / mid * 1e4; cur = self._sleeve.get(book_id, 0.0)
                    self._sleeve[book_id] = self.sleeve_q if u > self.sleeve_bp else (-self.sleeve_q if u < -self.sleeve_bp else cur)
                    self._sleeve_at[book_id] = self._sec
                target, cool = self._sleeve.get(book_id, 0.0), self.sleeve_cool
            gap = target - units
            if self.skip_flat and abs(gap) >= self.min_order_size(book_id) and self._sec - self._last_take.get(book_id, -10 ** 9) >= cool:
                side = OrderDirection.BUY if gap > 0 else OrderDirection.SELL
                q = round(min(abs(gap), self.take_size, qb if side == OrderDirection.SELL else qa), vd)
                px = bid if side == OrderDirection.SELL else ask
                funded = (acct.base_balance.free >= q) if side == OrderDirection.SELL else (acct.quote_balance.free >= q * px)
                if q >= self.min_order_size(book_id) and funded:
                    response.limit_order(book_id=book_id, direction=side, quantity=q, price=px, stp=STP.CANCEL_OLDEST, postOnly=False,
                                         timeInForce=TimeInForce.IOC)
                    self._last_take[book_id] = self._sec
            return
        if self.pace_cap and self._paced_out(int(book_id)):
            for o in acct.orders:                          # over the volume pace on this book: pull our quotes and wait
                response.cancel_order(book_id, o.id)
            return
        if self.toxic and self._toxic_update(book_id, book, self._sec, mid, tick):
            for o in acct.orders:                          # book paused: pull our quotes and stay out
                response.cancel_order(book_id, o.id)
            return
        units = acct.base_balance.total - base0 - tgt_units
        if self.max_units and units >= self.max_units:
            inv = max(inv, self.max_inv)                   # at the long cap: no more bids
        if self.max_units and units <= -self.max_units:
            inv = min(inv, -self.max_inv)                  # at the short cap: no more offers
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
        if self.pull and pred > self.pull * tick:
            want.pop(OrderDirection.SELL, None)            # price about to rise: do not leave an offer for a sniper to lift
        elif self.pull and pred < -self.pull * tick:
            want.pop(OrderDirection.BUY, None)             # price about to fall: do not leave a bid to be hit
        near = self._near.get(book_id, 0.0); until = self._pull_until.setdefault(book_id, {})
        if self.flow_pull and near > self.flow_pull:
            until[OrderDirection.SELL] = self._sec + self.flow_cool   # new orders crowding the bid near the touch: our offer gets lifted
        elif self.flow_pull and near < -self.flow_pull:
            until[OrderDirection.BUY] = self._sec + self.flow_cool
        for side, t in until.items():
            if self._sec <= t:
                want.pop(side, None)
        if self.trend_z and abs(trend) > self.trend_z and trend * inv < 0:
            want.pop(OrderDirection.BUY if inv > 0 else OrderDirection.SELL, None)   # long into a fall / short into a rise: unwind only
        # the validator adds 5-25 ms to every instruction after a book's first: cancel the side the prediction says is exposed first
        orders = sorted(acct.orders, key=lambda o: (o.side == OrderDirection.SELL) != (pred > 0)) if self.cancel_first else acct.orders
        for o in orders:
            px = want.get(o.side)
            behind = None if px is None else round(((px - o.price) if o.side == OrderDirection.BUY else (o.price - px)) / tick, 6)
            if px == o.price or (self.sticky and behind is not None and 0 <= behind <= self.sticky):
                want.pop(o.side)                      # at the target, or up to STICKY ticks less aggressive: keep its queue place (§1207)
            else:
                response.cancel_order(book_id, o.id)
        for side, px in want.items():
            response.limit_order(book_id=book_id, direction=side, quantity=sq.get(side, qty), price=px, stp=STP.CANCEL_BOTH, postOnly=True,
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
                    elif kind == "c" and e.side is not None:
                        of["c" + ("b" if e.side == 0 else "a")] += e.quantity or 0.0
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
    def _reserved(acct, side):
        """Funds our own resting orders on this side hold; they come back when we cancel and replace."""
        if side == OrderDirection.BUY:
            return sum(o.quantity * (o.price or 0.0) for o in acct.orders if o.side == OrderDirection.BUY)
        return sum(o.quantity for o in acct.orders if o.side == OrderDirection.SELL)


if __name__ == "__main__":
    launch(QuoteAgent)
