import json
sl = set(map(int, open("/opt/mvtrx/sleeve_books_x2.txt").read().split()))
with open("/opt/mvtrx/live_tape_x2.jsonl") as fh:
    fh.seek(0, 2); n = fh.tell(); fh.seek(max(0, n - 40_000_000)); fh.readline()
    r = [json.loads(l) for l in fh if '"p":' in l and "247" in l]
tm = max(x["ts"] for x in r); w = [x for x in r if x["ts"] > tm - 45e9]
tk = [x for x in w if x.get("Ta") == 247]; mk = [x for x in w if x.get("Ma") == 247]
print("x2 last 45 sim s: sleeve takes", len(tk), "on sleeve books", sum(x["book"] in sl for x in tk), "| vs x1:", sum(x.get("Ma") == 213 for x in tk),
      "| maker fills", len(mk), "on sleeve books", sum(x["book"] in sl for x in mk))
