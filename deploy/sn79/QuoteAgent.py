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

from taos.common.agents import launch
from taos.im.agents import FinanceAgent
from taos.im.protocol.models import OrderDirection, STP, TimeInForce


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
        self._mids, self._sflow = {}, {}                   # per book: {sec: mid} (last 125 s), {sec: signed taker qty} (last 6 s)
        self.trend_z = float(getattr(c, "trend_z", 0.0))   # >0: when the 120 s move exceeds TREND_Z standard deviations and inventory
                                                           # fights it, quote only the side that unwinds (§1194: losses sit on trending books)
        self.back = int(getattr(c, "back", 0))             # >0: rest BACK ticks behind the best price on both sides: snipers take the
                                                           # touch; fills that reach deeper come from large sweeps that tend to revert (§1199)
        self.pull = float(getattr(c, "pull", 0.0))         # >0: drop the quote on the side the model says the price will cross (|pred| > PULL ticks):
                                                           # live, other miners snipe stale quotes at −8 ticks each (§1199)
        self.toxic = float(getattr(c, "toxic", 0.0))       # >0: pause a book while our fills' 30 s markout EMA is below −TOXIC ticks
        self.toxic_pause = int(getattr(c, "toxic_pause", 180))   # sim seconds the book stays paused
        self._pending, self._mo, self._paused = {}, {}, {}  # per book: [(due sec, side, price)], markout EMA (ticks), paused until sec
        self.tape = open(str(c.tape), "a") if getattr(c, "tape", "") else None

    def respond_simulation(self, state):
        response = self.make_response()
        self._sec = state.timestamp // 1_000_000_000
        if self.tape is not None:
            self._record(state)
        for book_id, book in (state.books or {}).items():
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
        mids[sec] = mid
        for e in book.events or []:
            if getattr(e, "y", "") == "t":
                s = e.timestamp // 1_000_000_000
                fl[s] = fl.get(s, 0.0) + e.quantity * (1 if e.side == 0 else -1)
        for d, keep in ((mids, 125), (fl, 6)):
            for s in [s for s in d if s < sec - keep]:
                del d[s]
        if sec - 120 not in mids:
            return 0.0
        b, a = book.bids, book.asks
        def imb(k):
            bq, aq = sum(l.quantity for l in b[:k]), sum(l.quantity for l in a[:k])
            return (bq - aq) / (bq + aq) if bq + aq else 0.0
        micro = (b[0].price * a[0].quantity + a[0].price * b[0].quantity) / (b[0].quantity + a[0].quantity) - mid
        x = [sum(fl.get(sec - j, 0.0) for j in range(5)), mid - mids.get(sec - 5, mid), mid - mids.get(sec - 30, mid), mid - mids[sec - 120],
             imb(1), imb(5), micro]
        m = self.model
        return sum(w * (v - mu) / sd for w, v, mu, sd in zip(m["w"], x, m["mu"], m["sd"]) if sd > 0)

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
        qty = round(max(self.size * wealth0 / mid, self.min_order_size(book_id)), vd)
        want = {}
        if self.toxic and self._toxic_update(book_id, book, self._sec, mid, tick):
            for o in acct.orders:                          # book paused: pull our quotes and stay out
                response.cancel_order(book_id, o.id)
            return
        if inv < self.max_inv and acct.quote_balance.free + self._reserved(acct, OrderDirection.BUY) >= qty * bid_px:
            want[OrderDirection.BUY] = bid_px
        if inv > -self.max_inv and acct.base_balance.free + self._reserved(acct, OrderDirection.SELL) >= qty:
            want[OrderDirection.SELL] = ask_px
        if self.pull and pred > self.pull * tick:
            want.pop(OrderDirection.SELL, None)            # price about to rise: do not leave an offer for a sniper to lift
        elif self.pull and pred < -self.pull * tick:
            want.pop(OrderDirection.BUY, None)             # price about to fall: do not leave a bid to be hit
        if self.trend_z and abs(trend) > self.trend_z and trend * inv < 0:
            want.pop(OrderDirection.BUY if inv > 0 else OrderDirection.SELL, None)   # long into a fall / short into a rise: unwind only
        for o in acct.orders:
            if want.get(o.side) == o.price:
                want.pop(o.side)                      # already resting at the target price: keep its queue place
            else:
                response.cancel_order(book_id, o.id)
        for side, px in want.items():
            response.limit_order(book_id=book_id, direction=side, quantity=qty, price=px, stp=STP.CANCEL_BOTH, postOnly=True,
                                 timeInForce=TimeInForce.GTT, expiryPeriod=self.expiry)

    def _record(self, state):
        ts = state.timestamp
        for book_id, book in (state.books or {}).items():
            for e in book.events or []:
                if getattr(e, "y", "") == "t":
                    self.tape.write(json.dumps({"ts": e.timestamp, "book": book_id, "id": e.id, "p": e.price, "q": e.quantity, "s": e.side,
                                                "Ma": e.Ma, "Ta": e.Ta, "Mf": e.Mf, "Tf": e.Tf}) + "\n")
            if book.bids and book.asks:
                self.tape.write(json.dumps({"ts": ts, "book": book_id, "bid": book.bids[0].price, "ask": book.asks[0].price,
                                            "bids": [[l.price, l.quantity] for l in book.bids[:5]], "asks": [[l.price, l.quantity] for l in book.asks[:5]],
                                            "fund": getattr(book, "fundamental", None) or getattr(book, "f", None)}) + "\n")
        self.tape.flush()

    @staticmethod
    def _reserved(acct, side):
        """Funds our own resting orders on this side hold; they come back when we cancel and replace."""
        if side == OrderDirection.BUY:
            return sum(o.quantity * (o.price or 0.0) for o in acct.orders if o.side == OrderDirection.BUY)
        return sum(o.quantity for o in acct.orders if o.side == OrderDirection.SELL)


if __name__ == "__main__":
    launch(QuoteAgent)
