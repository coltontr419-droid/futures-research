"""MVTRX (SN79) market maker for the lab (futures-research decisions.md §1193).

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
        self.tape = open(str(c.tape), "a") if getattr(c, "tape", "") else None

    def respond_simulation(self, state):
        response = self.make_response()
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
        inside = spread > 2.5 * tick
        bid_px = min(bid + tick if inside else bid, fair - self.edge * tick, ask - tick)
        ask_px = max(ask - tick if inside else ask, fair + self.edge * tick, bid + tick)
        bid_px = round(round(bid_px / tick) * tick, pd)
        ask_px = round(round(ask_px / tick) * tick, pd)
        qty = round(max(self.size * wealth0 / mid, self.min_order_size(book_id)), vd)
        want = {}
        if inv < self.max_inv and acct.quote_balance.free + self._reserved(acct, OrderDirection.BUY) >= qty * bid_px:
            want[OrderDirection.BUY] = bid_px
        if inv > -self.max_inv and acct.base_balance.free + self._reserved(acct, OrderDirection.SELL) >= qty:
            want[OrderDirection.SELL] = ask_px
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
