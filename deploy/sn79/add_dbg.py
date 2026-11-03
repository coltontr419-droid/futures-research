p = "/opt/mvtrx/agents/QuoteAgent.py"; s = open(p).read()
assert "self.dbg" not in s
a = """        self.fit_qty = int(getattr(c, "fit_qty", 0))"""
b = a + """
        self.dbg = int(getattr(c, "dbg", 0)); self._dbg_at = {}   # 1: log per quoted book once a minute (inventory, balances, wanted sides)"""
assert s.count(a) == 1; s = s.replace(a, b)
a2 = """        if self.take and abs(pred) > self.take * tick"""
b2 = """        if self.dbg and self._sec - self._dbg_at.get(book_id, -10 ** 9) >= 60:
            self._dbg_at[book_id] = self._sec
            bt.logging.info(f"DBG book {book_id} mid {mid:.4f} units {units:.1f} inv {inv:+.3f} qty {qty} qfree {acct.quote_balance.free:.1f} "
                            f"bfree {acct.base_balance.free:.1f} base0 {base0:.1f} wealth0 {wealth0:.0f} bid_px {bid_px} ask_px {ask_px} want {sorted(int(k) for k in want)} pred {pred:+.2f}")
""" + a2
assert s.count(a2) == 1; s = s.replace(a2, b2); open(p, "w").write(s); print("patched")
