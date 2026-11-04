import sys
p = sys.argv[1]; s = open(p).read()
assert "sleeve_dm" not in s
a = """        self.sleeve_band = float(getattr(c, "sleeve_band", 0.2))"""
b = a + """
        self.sleeve_dm = float(getattr(c, "sleeve_dm", 0.0))      # >0: use the gap minus its own EMA (half-life sleeve_dm sim s) — volatile books sit
        self.sleeve_sign = float(getattr(c, "sleeve_sign", 1.0))  # hundreds of bp from the fundamental; -1 trades WITH the deviation (§1211 add. 27)
        self._gap_ema = {}"""
assert s.count(a) == 1; s = s.replace(a, b)
a2 = """                    u = (fundamental - mid) / mid * 1e4; cur = self._sleeve.get(book_id, 0.0)"""
b2 = """                    u = (fundamental - mid) / mid * 1e4; cur = self._sleeve.get(book_id, 0.0)
                    if self.sleeve_dm > 0:
                        e = self._gap_ema.get(book_id, u); e = e + (1 - 0.5 ** (self.sleeve_step / self.sleeve_dm)) * (u - e)
                        self._gap_ema[book_id] = e; u = u - e
                    u = u * self.sleeve_sign"""
assert s.count(a2) == 1; s = s.replace(a2, b2); open(p, "w").write(s); print("patched", p)
