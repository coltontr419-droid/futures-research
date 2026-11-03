import sys
p = sys.argv[1]; s = open(p).read()
assert "sleeve_bp" not in s
a = """        self.skip_flat = int(getattr(c, "skip_flat", 0))"""
b = a + """
        self.sleeve_bp = float(getattr(c, "sleeve_bp", 0.0))   # >0 (with skip_flat): on skipped books steer the position to ±SLEEVE_Q by the sign of
        self.sleeve_q = float(getattr(c, "sleeve_q", 10.0))     # (fundamental − mid)/mid beyond ±SLEEVE_BP (hysteresis), checked every SLEEVE_STEP
        self.sleeve_step = int(getattr(c, "sleeve_step", 10))   # sim s, one IOC per SLEEVE_COOL s: de-beta skill counts held inventory × Δmid
        self.sleeve_cool = int(getattr(c, "sleeve_cool", 5))    # and its 2.3 bp hurdle is per own notional (§1211 add. 20)
        self._sleeve, self._sleeve_at = {}, {}"""
assert s.count(a) == 1; s = s.replace(a, b)
a2 = """            units = acct.base_balance.total - base0
            if self.skip_flat and abs(units) >= self.min_order_size(book_id) and self._sec - self._last_take.get(book_id, -10 ** 9) >= self.take_cool:
                side = OrderDirection.SELL if units > 0 else OrderDirection.BUY
                q = round(min(abs(units), self.take_size, qb if side == OrderDirection.SELL else qa), vd)"""
b2 = """            units = acct.base_balance.total - base0
            target, cool = 0.0, self.take_cool
            if self.sleeve_bp and fundamental:
                if self._sec - self._sleeve_at.get(book_id, -10 ** 9) >= self.sleeve_step:
                    u = (fundamental - mid) / mid * 1e4; cur = self._sleeve.get(book_id, 0.0)
                    self._sleeve[book_id] = self.sleeve_q if u > self.sleeve_bp else (-self.sleeve_q if u < -self.sleeve_bp else cur)
                    self._sleeve_at[book_id] = self._sec
                target, cool = self._sleeve.get(book_id, 0.0), self.sleeve_cool
            gap = target - units
            if self.skip_flat and abs(gap) >= self.min_order_size(book_id) and self._sec - self._last_take.get(book_id, -10 ** 9) >= cool:
                side = OrderDirection.BUY if gap > 0 else OrderDirection.SELL
                q = round(min(abs(gap), self.take_size, qb if side == OrderDirection.SELL else qa), vd)"""
assert s.count(a2) == 1, s.count(a2); s = s.replace(a2, b2); open(p, "w").write(s); print("patched", p)
