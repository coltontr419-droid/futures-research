import json, types, sys
sys.path.insert(0, "/opt/mvtrx/repo")
import importlib.util
spec = importlib.util.spec_from_file_location("QAc", "/tmp/QA_calm.py"); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
L = types.SimpleNamespace
o = L(calm_k=40, calm_hl=300.0, _calm_last={}, _calm_vol={}, _calm_t0=None, _calm_at=-1, skip=set(), _sec=0, _books={})
upd = mod.QuoteAgent._calm_update
static = set(range(128)) - set(map(int, open("/opt/mvtrx/skip_books.txt").read().split()))
cur = None; checks = []
for line in open("/opt/mvtrx/live_tape_x1_size6.jsonl"):
    if "\"bid\"" not in line: continue
    r = json.loads(line)
    if not (r.get("bid") and r.get("ask")): continue
    sec = r["ts"] // 10**9
    if cur is not None and sec != cur:
        o._sec = cur; upd(o)
        if o._calm_at == cur and (not checks or cur - checks[-1][0] >= 600):
            chosen = set(range(128)) - o.skip; checks.append((cur, len(chosen & static)))
    cur = sec
    o._books[r["book"]] = L(bids=[L(price=r["bid"])], asks=[L(price=r["ask"])])
print("sim min : overlap of online calm-40 with the validated static list")
for t, n in checks: print(f"  {t/60:6.1f} : {n}/40")
v = o._calm_vol; chosen = sorted(set(range(128)) - o.skip)
print("online chosen:", chosen)
print("vol bp by group: 0-62 med %.2f | 63-101 med %.2f | 102-127 med %.2f" % tuple(sorted(v[b] for b in v if lo <= b <= hi)[len([b for b in v if lo <= b <= hi])//2] for lo, hi in ((0,62),(63,101),(102,127))))
print("samples per book (last):", {b: o._calm_last[b][0] for b in list(o._calm_last)[:3]}, "now", o._sec)
