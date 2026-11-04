import sys
p = sys.argv[1]; s = open(p).read()
assert "sleeve_prop" not in s
a = """        self._sleeve, self._sleeve_at = {}, {}"""
b = a + """
        self.sleeve_prop = float(getattr(c, "sleeve_prop", 0.0))   # >0: proportional sleeve — target = sleeve_q × clip(gap_bp / sleeve_prop, ±1),
        self.sleeve_band = float(getattr(c, "sleeve_band", 0.2))   # changed only when it moves > sleeve_band × sleeve_q (§1211 add. 27): de-beta
                                                                   # alpha comes from position CHANGES (a held position strips to zero)"""
assert s.count(a) == 1; s = s.replace(a, b)
a2 = """                    self._sleeve[book_id] = self.sleeve_q if u > self.sleeve_bp else (-self.sleeve_q if u < -self.sleeve_bp else cur)"""
b2 = """                    if self.sleeve_prop > 0:
                        tgt = self.sleeve_q * max(-1.0, min(1.0, u / self.sleeve_prop))
                        self._sleeve[book_id] = tgt if abs(tgt - cur) >= self.sleeve_band * self.sleeve_q else cur
                    else:
                        self._sleeve[book_id] = self.sleeve_q if u > self.sleeve_bp else (-self.sleeve_q if u < -self.sleeve_bp else cur)"""
assert s.count(a2) == 1; s = s.replace(a2, b2); open(p, "w").write(s); print("patched", p)
