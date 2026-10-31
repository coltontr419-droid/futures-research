"""BEX Tracer feasibility (decisions.md §1203): which of the 89 pool extensions can touch an arbitrary https page at all, from manifest.json."""
import json, os, sys, yaml, collections
root, pool = sys.argv[1], yaml.safe_load(open(sys.argv[2]))["pool"]
GENERIC = ("<all_urls>", "*://*/*", "https://*/*", "http://*/*")
def generic(m): return any(g in m or m.startswith("*://*/") or m.startswith("https://*/") for g in GENERIC)
dirs = {}
for d in os.listdir(root):
    p = os.path.join(root, d, "manifest.json")
    if os.path.exists(p): dirs[d] = p
rows = collections.defaultdict(list); counts = collections.Counter()
for e in pool:
    path = next((p for d, p in dirs.items() if e["id"] in d), None)
    if not path:
        rows[e["group"]].append((e["name"], "manifest not found")); continue
    m = json.load(open(path, encoding="utf-8-sig"))
    cs = m.get("content_scripts") or []
    cs_all = [c for c in cs if any(generic(x) for x in c.get("matches", []))]
    main_world = any(c.get("world") == "MAIN" for c in cs_all)
    perms = set(m.get("permissions", [])) | set(m.get("host_permissions", [])) | set(m.get("optional_permissions", []))
    dnr = "declarativeNetRequest" in perms or "declarativeNetRequestWithHostAccess" in perms or bool(m.get("declarative_net_request"))
    dnr_static = bool((m.get("declarative_net_request") or {}).get("rule_resources"))
    webreq = "webRequest" in perms or "webRequestBlocking" in perms
    all_hosts = any(generic(x) for x in perms)
    if cs_all and main_world: tag = "A: page-world script on all sites"
    elif cs_all: tag = "B: content script on all sites"
    elif dnr_static or (dnr and all_hosts) or (webreq and all_hosts and m.get("manifest_version") == 2): tag = "C: network rules only"
    elif cs: tag = "D: content script on specific sites only"
    else: tag = "E: no page access (toolbar/background only)"
    counts[tag[0]] += 1; rows[e["group"]].append((e["name"], tag))
for g, v in rows.items():
    print(f"== {g}")
    for n, t in v: print(f"   {t[:2]} {n}")
print("\nTOTAL:", dict(sorted(counts.items())), "of", len(pool))
