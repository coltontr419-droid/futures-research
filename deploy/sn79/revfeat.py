"""Live features for the §1233 reversal predictor, computed the same way as predfeat.py (per book, 1-second resolution, forward-filled).
Shared by QuoteAgent (live) and revfeat_parity.py (tape replay vs the training rows)."""
import json, math
from collections import deque

TOP = {114, 238, 120, 163, 42, 214, 191, 89, 113, 124, 243, 70, 8, 103, 159, 161, 170, 126, 150, 100}


class _Series:
    """value per second, forward-filled lookup of the last value at or before a second; keeps KEEP seconds."""
    __slots__ = ("d", "keep")

    def __init__(self, keep=330):
        self.d = deque(); self.keep = keep

    def set(self, t, v):
        if self.d and self.d[-1][0] == t:
            self.d[-1] = (t, v)
        else:
            self.d.append((t, v))
        while self.d and self.d[0][0] < t - self.keep:
            self.d.popleft()

    def at(self, t):
        for k, v in reversed(self.d):
            if k <= t:
                return v
        return None


class _Sums:
    """per-second sums (signed flow, book flow, big trades) and a long running mean of |per-second value| (zeros included)."""
    __slots__ = ("d", "last", "mabs", "n")

    def __init__(self):
        self.d = {}; self.last = None; self.mabs = 0.0; self.n = 0

    def add(self, t, v):
        self.d[t] = self.d.get(t, 0.0) + v

    def close_to(self, t):
        """fold every finished second before t into the running mean of |value|, then forget old seconds."""
        if self.last is None:
            self.last = t
        while self.last < t:
            v = abs(self.d.get(self.last, 0.0)); self.n += 1; self.mabs += (v - self.mabs) / min(self.n, 3600)
            self.last += 1
        for k in [k for k in self.d if k < t - 20]:
            del self.d[k]

    def window(self, t, w):
        return sum(self.d.get(k, 0.0) for k in range(t - w, t))


class RevFeatures:
    def __init__(self, model_path, warm_s=600):
        m = json.load(open(model_path)); self.warm_s = warm_s
        self.names, self.mu, self.sd, self.w, self.b, self.th = m["names"], m["mu"], m["sd"], m["w"], m["b"], m["th_top2pct"]
        self.books = {}

    def _bk(self, b):
        s = self.books.get(b)
        if s is None:
            s = self.books[b] = {"mid": _Series(), "fund": _Series(), "flow": _Sums(), "book": _Sums(), "big": _Sums(), "sizes": deque(maxlen=3000), "p95": None, "p95_at": -10 ** 9}
        return s

    def update(self, b, t, mid, fund, imb, spread, trades=(), of=0.0, own_uid=None):
        """t: sim second; trades: iterable of (second, price, qty, taker_uid) since the last update (each filed under its own second);
        of: new-minus-cancelled book flow in second t."""
        s = self._bk(b)
        s["mid"].set(t, mid)
        if fund:
            s["fund"].set(t, fund)
        s["imb"], s["spread"] = imb, spread
        for te, p, q, ta in trades:
            if ta in TOP or (own_uid is not None and ta == own_uid):
                continue
            ref = s["mid"].at(te - 1); ref = ref if ref is not None else mid
            sg = 1.0 if p >= ref else -1.0; s["flow"].add(te, sg * q); s["sizes"].append(q)
            if s["p95"] is not None and q >= s["p95"]:
                s["big"].add(te, sg)
        if t - s["p95_at"] >= 60 and len(s["sizes"]) >= 50:
            xs = sorted(s["sizes"]); s["p95"] = xs[int(0.95 * (len(xs) - 1))]; s["p95_at"] = t
        if of:
            s["book"].add(t, of)
        for k in ("flow", "book", "big"):                  # after this second's trades are filed: fold finished seconds into the means
            s[k].close_to(t)

    def features(self, b, t):
        s = self.books.get(b)
        if s is None:
            return None
        M, F = s["mid"], s["fund"]
        m = M.at(t); f0 = F.at(t)
        vals = [M.at(t - k) for k in (1, 5, 30, 60, 300)] + [F.at(t - k) for k in (1, 10, 60)] + [F.at(t - 10), M.at(t - 10)]
        if m is None or f0 is None or any(v is None for v in vals) or not m:
            return None
        bp = lambda a, z: (a - z) / m * 1e4
        m1, m5, m30, m60, m300, f1, f10, f60, f10b, m10 = vals
        g = bp(f0, m); g10 = g - bp(f10b, m10)
        fl, bk = s["flow"], s["book"]
        warm = lambda z: z.n >= self.warm_s and z.mabs > 0                # flow scales need WARM_S seconds of history (else 0 = the mean)
        return [bp(m, m1), bp(m, m5), bp(m, m30), bp(m, m60), bp(m, m300), bp(f0, f1), bp(f0, f10), bp(f0, f60), g, g10, s["imb"], s["spread"],
                fl.window(t, 10) / (fl.mabs * 10) if warm(fl) else 0.0, bk.window(t, 10) / (bk.mabs * 10) if warm(bk) else 0.0,
                s["big"].window(t, 5) if s["p95"] is not None else 0.0]

    def predict(self, b, t):
        x = self.features(b, t)
        if x is None:
            return None
        z = [max(-6.0, min(6.0, (v - mu) / sd)) for v, mu, sd in zip(x, self.mu, self.sd)]
        return self.b + sum(a * c for a, c in zip(z, self.w))
