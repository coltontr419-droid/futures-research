import sys
p = sys.argv[1]; s = open(p).read()
assert "tilt_bp" not in s
a = """        self.fit_qty = int(getattr(c, "fit_qty", 0))"""
b = a + """
        self.tilt_bp = float(getattr(c, "tilt_bp", 0.0))   # >0: on quoted books the inventory target is ±TILT_NOTIONAL $ by the sign of (fundamental − mid)
        self.tilt_notional = float(getattr(c, "tilt_notional", 5000.0))   # beyond ±TILT_BP (hysteresis, re-checked every sleeve_step); skew and the
        self._tilt, self._tilt_at = {}, {}                 # unit caps act around it — de-beta skill on making books (§1211 add. 23)"""
assert s.count(a) == 1; s = s.replace(a, b)
a2 = """        inv = (acct.base_balance.total - base0) * mid / wealth0
"""
b2 = a2 + """        tgt_units = 0.0
        if self.tilt_bp:
            f0 = getattr(book, "fundamental", None) or getattr(book, "f", None)
            if f0:
                if self._sec - self._tilt_at.get(book_id, -10 ** 9) >= self.sleeve_step:
                    u = (f0 - mid) / mid * 1e4; cur = self._tilt.get(book_id, 0.0)
                    self._tilt[book_id] = 1.0 if u > self.tilt_bp else (-1.0 if u < -self.tilt_bp else cur)
                    self._tilt_at[book_id] = self._sec
                tgt_units = self._tilt.get(book_id, 0.0) * self.tilt_notional / mid
                inv = (acct.base_balance.total - base0 - tgt_units) * mid / wealth0
"""
assert s.count(a2) == 1; s = s.replace(a2, b2)
a3 = """        units = acct.base_balance.total - base0
        if self.max_units and units >= self.max_units:"""
b3 = """        units = acct.base_balance.total - base0 - tgt_units
        if self.max_units and units >= self.max_units:"""
assert s.count(a3) == 1; s = s.replace(a3, b3); open(p, "w").write(s); print("patched", p)
