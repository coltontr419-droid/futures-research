import json, re, sys
txt = open(sys.argv[1]).read()
for block in re.split(r"^== ", txt, flags=re.M)[1:]:
    head, rest = block.split("\n", 1)
    if head.startswith("ce"): continue
    try: d = json.loads(rest[rest.index("{"):rest.rindex("}") + 1])
    except Exception: print(head, "ERROR"); continue
    for m, v in d.items(): print(f"{head:9} {m:30} prompts {v.get('prompts')} | share {v.get('share_pct')}% vs median UID {v.get('median_share_pct')}%")
