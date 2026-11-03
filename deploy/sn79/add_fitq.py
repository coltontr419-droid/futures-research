import sys
p = sys.argv[1]; s = open(p).read()
assert "fit_qty" not in s
a = """        if bid_px is not None and inv < self.max_inv and acct.quote_balance.free + self._reserved(acct, OrderDirection.BUY) >= qty * bid_px:
            want[OrderDirection.BUY] = bid_px
        if ask_px is not None and inv > -self.max_inv and acct.base_balance.free + self._reserved(acct, OrderDirection.SELL) >= qty:
            want[OrderDirection.SELL] = ask_px"""
b = """        sq = {}                                           # per-side quantity (fit_qty: the affordable part of qty, §1211 add. 21)
        if bid_px is not None and inv < self.max_inv:
            room = (acct.quote_balance.free + self._reserved(acct, OrderDirection.BUY)) / bid_px
            q = qty if room >= qty else (round(room * 0.98, vd) if self.fit_qty else 0.0)
            if q >= self.min_order_size(book_id) and q > 0:
                want[OrderDirection.BUY] = bid_px; sq[OrderDirection.BUY] = q
        if ask_px is not None and inv > -self.max_inv:
            room = acct.base_balance.free + self._reserved(acct, OrderDirection.SELL)
            q = qty if room >= qty else (round(room * 0.98, vd) if self.fit_qty else 0.0)
            if q >= self.min_order_size(book_id) and q > 0:
                want[OrderDirection.SELL] = ask_px; sq[OrderDirection.SELL] = q"""
assert s.count(a) == 1; s = s.replace(a, b)
a2 = """            response.limit_order(book_id=book_id, direction=side, quantity=qty, price=px, stp=STP.CANCEL_BOTH, postOnly=True,"""
b2 = """            response.limit_order(book_id=book_id, direction=side, quantity=sq.get(side, qty), price=px, stp=STP.CANCEL_BOTH, postOnly=True,"""
assert s.count(a2) == 1; s = s.replace(a2, b2)
a3 = """        self.skip_flat = int(getattr(c, "skip_flat", 0))"""
b3 = a3 + """
        self.fit_qty = int(getattr(c, "fit_qty", 0))      # 1: quote the affordable part of the order instead of skipping the side (§1211 add. 21)"""
assert s.count(a3) == 1; s = s.replace(a3, b3); open(p, "w").write(s); print("patched", p)
