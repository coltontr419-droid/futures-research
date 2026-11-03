import sys
p = sys.argv[1]; s = open(p).read()
assert "pace_cap" not in s
a = """        self.fit_qty = int(getattr(c, "fit_qty", 0))"""
b = a + """
        # pace (§1211 add. 21): the validator drops a miner's placements on a book once its traded notional over the last 24 sim h reaches
        # capital_turnover_cap (10) × miner wealth (≈ $500k per book). Quote a book only while the trailing PACE_PERIOD sum < PACE_CAP and the
        # trailing PACE_WIN sum < PACE_CAP × PACE_WIN / PACE_PERIOD × PACE_K (even spending). Seeded from our own tape at start-up.
        self.pace_cap = float(getattr(c, "pace_cap", 0.0)); self.pace_period = int(getattr(c, "pace_period", 86400))
        self.pace_win = int(getattr(c, "pace_win", 5400)); self.pace_k = float(getattr(c, "pace_k", 1.0))
        self._pace, self._pace_seen = defaultdict(list), set()
        if self.pace_cap and getattr(c, "tape", ""):
            try:
                rows = []
                for line in open(str(c.tape)):
                    if '"p":' in line and str(self.uid) in line:
                        r = json.loads(line)
                        if r.get("Ma") == self.uid or r.get("Ta") == self.uid:
                            rows.append((r["ts"] // 1_000_000_000, r["book"], r["p"] * r["q"], (r["book"], r.get("id"), r["ts"])))
                end = max((x[0] for x in rows), default=0)
                for sec, bk, v, key in rows:
                    if sec > end - self.pace_period and key not in self._pace_seen:
                        self._pace_seen.add(key); self._pace[bk].append((sec, v))
                bt.logging.info(f"PACE seeded {sum(len(v) for v in self._pace.values())} own fills on {len(self._pace)} books from the tape")
            except Exception as e:
                bt.logging.warning(f"PACE seed failed: {e}")"""
assert s.count(a) == 1; s = s.replace(a, b)
a2 = """        if self.tape is not None:
            self._record(state)
        for book_id, book in"""
b2 = """        if self.tape is not None:
            self._record(state)
        if self.pace_cap:
            for book_id, book in (self._books if self._books is not None else state.books or {}).items():
                for e in book.events or []:
                    if getattr(e, "y", "") == "t" and (e.Ma == self.uid or e.Ta == self.uid):
                        key = (int(book_id), e.id, e.timestamp)
                        if key not in self._pace_seen:
                            self._pace_seen.add(key); self._pace[int(book_id)].append((e.timestamp // 1_000_000_000, e.price * e.quantity))
        for book_id, book in"""
assert s.count(a2) == 1; s = s.replace(a2, b2)
a3 = """        if self.toxic and self._toxic_update(book_id, book, self._sec, mid, tick):"""
b3 = """        if self.pace_cap and self._paced_out(int(book_id)):
            for o in acct.orders:                          # over the volume pace on this book: pull our quotes and wait
                response.cancel_order(book_id, o.id)
            return
""" + a3
assert s.count(a3) == 1; s = s.replace(a3, b3)
a4 = """    def _toxic_update(self, book_id, book, sec, mid, tick):"""
b4 = """    def _paced_out(self, book_id):
        h = self._pace.get(book_id)
        if not h:
            return False
        lo = self._sec - self.pace_period
        if h[0][0] <= lo:
            self._pace[book_id] = h = [x for x in h if x[0] > lo]
        day = sum(v for _, v in h); recent = sum(v for t, v in h if t > self._sec - self.pace_win)
        return day >= self.pace_cap or recent >= self.pace_cap * self.pace_win / self.pace_period * self.pace_k

""" + a4
assert s.count(a4) == 1; s = s.replace(a4, b4); open(p, "w").write(s); print("patched", p)
