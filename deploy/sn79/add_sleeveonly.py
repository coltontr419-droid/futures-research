p = "/opt/mvtrx/agents/QuoteAgent.py"; s = open(p).read()
a = """            units = acct.base_balance.total - base0
            target, cool = 0.0, self.take_cool"""
b = """            if self.sleeve_books is not None and int(book_id) not in self.sleeve_books:
                return                                     # sleeve_file set: trade only the sleeve books (another UID of ours quotes the rest)
            units = acct.base_balance.total - base0
            target, cool = 0.0, self.take_cool"""
assert s.count(a) == 1; open(p, "w").write(s.replace(a, b)); print("patched")
