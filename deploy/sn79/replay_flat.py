"""Replay check for skip_file / skip_flat (§1211 add. 8-9): without them the new agent reproduces the pre-skip agent exactly; with them, on a
skipped book the only instructions are cancels and reducing-side IOCs no larger than the position.  python replay_flat.py <pre-skip.py> <new.py>"""
import json, sys
sys.argv += []
exec(open("/opt/mvtrx/replay_own.py").read().split("live, _ = run")[0])
SKIP = "/opt/mvtrx/skip_books.txt"; skip = set(map(int, open(SKIP).read().split()))
old, _ = run(sys.argv[1], own_ex=1); new, _ = run(sys.argv[2], own_ex=1)
print("no skip params: identical to the pre-skip agent:", old == new, "| instructions", sum(map(len, old)))
flat, a = run(sys.argv[2], own_ex=1, skip_file=SKIP, skip_flat=1)
bad = kinds = 0; iocs = []
for st in flat:
    for s in st:
        i = json.loads(s); b = i.get("bookId", i.get("book_id"))
        if b is None or int(b) not in skip:
            continue
        kinds += 1
        t = json.dumps(i)
        if "IOC" in t or '"timeInForce": "IOC"' in t or "ioc" in t.lower():
            iocs.append(i)
        elif "cancel" not in t.lower():
            bad += 1
print(f"skip+flat: instructions on skipped books {kinds} | IOC unwinds {len(iocs)} | resting/other orders on skipped books {bad}")
if iocs:
    print("example IOC:", {k: v for k, v in iocs[0].items() if k in ("bookId", "direction", "quantity", "price", "timeInForce", "type")})
seen = set()
for st in flat:
    for s in st:
        i = json.loads(s); b = i.get("bookId", i.get("book_id"))
        if b is not None and int(b) in skip and "cancel" not in s.lower():
            k = tuple(sorted(i.keys()))
            if k not in seen: seen.add(k); print(s[:400])
ns = [json.loads(s) for st in flat for s in st if "cancel" not in s.lower() and json.loads(s).get("bookId") is not None and int(json.loads(s)["bookId"]) in skip]
print("of", len(ns), "-> IOC (tif 2, not postOnly):", sum(i["timeInForce"] == 2 and not i["postOnly"] for i in ns), "| max qty", max(i["quantity"] for i in ns), "| books", len({i["bookId"] for i in ns}))
