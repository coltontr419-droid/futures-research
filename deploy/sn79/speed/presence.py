"""Books with our resting orders per state (tape 'queue' lines), averaged per sim window.  stdin = grep '"queue"' lines."""
import sys, json, collections
W = [(a, b, n) for a, b, n in (x.split(":") for x in sys.argv[1:])]
per = collections.defaultdict(set)
for l in sys.stdin:
    i = l.find('"ts": '); ts = int(l[i + 6:l.index(",", i)]) // 10**9
    j = l.find('"book": '); bk = int(l[j + 8:l.index(",", j)]); per[ts].add(bk)
for a, b, n in W:
    a, b = int(a), int(b); xs = [len(v) for t, v in per.items() if a <= t < b]
    if not xs: print(n, "no states"); continue
    xs.sort(); print(f"{n:28} states {len(xs):4d} | books with our resting orders: median {xs[len(xs)//2]:3d}  p10 {xs[len(xs)//10]:3d}  max {xs[-1]:3d}")
