import json
exec(open("/opt/mvtrx/replay_own.py").read().split("live, _ = run")[0])
kw = dict(own_ex=1, skip_file="/tmp/books_all.txt", sleeve_file="/tmp/books_all.txt", skip_flat=1, take_size=25, sleeve_cool=5, rev_usd=1000,
          sleeve_bp=4, rev_look=300, rev_hold=600, sleeve_step=3600)
for v in (-9.0, 0.17, 0.99):
    r, a = run("/tmp/QA_imb.py", rev_imb=v, **kw)
    ent = sum(1 for t, at in a._rev.values() if at > -10 ** 9)
    imbs = [round(a._depth_imb(b), 2) for b in list((a._books or {}).values())[:5]] if getattr(a, "_books", None) else "n/a"
    print("rev_imb %+.2f: placements %d | books with an entry %d | sample imbalances %s" % (v, sum(1 for st in r for x in st if "PLACE" in x), ent, imbs))
