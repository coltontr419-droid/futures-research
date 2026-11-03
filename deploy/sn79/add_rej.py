p = "/opt/mvtrx/agents/QuoteAgent.py"; s = open(p).read()
assert "def onOrderRejected" not in s
a = """    def _calm_update(self):"""
b = """    def onOrderRejected(self, event):
        \"\"\"dbg: count the exchange's placement rejections by message, logged once a minute (§1211 add. 21).\"\"\"
        if not getattr(self, "dbg", 0):
            return
        from collections import Counter
        self._rej = getattr(self, "_rej", Counter()); self._rej[str(getattr(event, "message", "?"))] += 1
        if self._sec - getattr(self, "_rej_at", -10 ** 9) >= 60:
            self._rej_at = self._sec; bt.logging.info(f"DBG REJECTS {dict(self._rej)}"); self._rej.clear()

""" + a
assert s.count(a) == 1; s = s.replace(a, b); open(p, "w").write(s); print("patched")
