p = "/opt/mvtrx/agents/QuoteAgent.py"; s = open(p).read()
assert "calm_k" not in s
a = """        self.skip_flat = int(getattr(c, "skip_flat", 0))"""
b = """        self.calm_k = int(getattr(c, "calm_k", 0))         # >0: quote only the CALM_K books with the lowest volatility EMA (mean |Δmid| over 10 s,
        self.calm_hl = float(getattr(c, "calm_hl", 300))   # half-life CALM_HL sim s), re-chosen every 60 sim s after CALM_HL sim s of warm-up;
        self._calm_last, self._calm_vol, self._calm_t0, self._calm_at = {}, {}, None, -1   # until then skip_file applies (§1211 add. 11)
""" + a
assert s.count(a) == 1; s = s.replace(a, b)
a2 = """        for book_id, book in (self._books if self._books is not None else state.books or {}).items():
            acct = self.accounts.get(book_id)"""
b2 = """        if self.calm_k:
            self._calm_update()
""" + a2
assert s.count(a2) == 1; s = s.replace(a2, b2)
a3 = """    def _toxic_update(self, book_id, book, sec, mid, tick):"""
b3 = """    def _calm_update(self):
        \"\"\"Per book: EMA of |mid now − mid ≥ 10 s ago|; after warm-up, skip every book outside the calm_k lowest (book ids are market
        regimes, §1211 add. 10: only the calm ones make money; one 10-sim-min slice keeps 33 of the next slice's 40 calmest).\"\"\"
        books = self._books if self._books is not None else {}
        if self._calm_t0 is None:
            self._calm_t0 = self._sec
        w = 1 - 0.5 ** (10 / self.calm_hl)
        for book_id, book in books.items():
            if not book.bids or not book.asks:
                continue
            mid = (book.bids[0].price + book.asks[0].price) / 2
            last = self._calm_last.get(book_id)
            if last is None:
                self._calm_last[book_id] = (self._sec, mid)
            elif self._sec - last[0] >= 10:
                v = abs(mid - last[1]) * 100                      # cents, NOT bp: the calm books are the ≈ $30 ones where the 1 c tick is wide (§1211 add. 11)
                old = self._calm_vol.get(book_id)
                self._calm_vol[book_id] = v if old is None else old + w * (v - old)
                self._calm_last[book_id] = (self._sec, mid)
        if self._sec - self._calm_t0 >= self.calm_hl and self._sec - self._calm_at >= 60 and len(self._calm_vol) >= self.calm_k:
            calm = set(sorted(self._calm_vol, key=self._calm_vol.get)[:self.calm_k])
            self.skip = {int(b) for b in self._calm_vol if b not in calm}
            self._calm_at = self._sec

""" + a3
assert s.count(a3) == 1; s = s.replace(a3, b3); open(p, "w").write(s); print("patched")
