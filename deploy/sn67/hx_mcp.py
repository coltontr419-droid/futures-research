import json, sys, urllib.request
U = "https://api.harnyx.ai/mcp"; H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "User-Agent": "mcp-client/1.0"}
def call(method, params, sid=None, i=1):
    h = dict(H); 
    if sid: h["Mcp-Session-Id"] = sid
    req = urllib.request.Request(U, json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}).encode(), h)
    with urllib.request.urlopen(req, timeout=60) as r:
        sid = r.headers.get("Mcp-Session-Id") or sid; body = r.read().decode()
    if body.startswith("event:") or "data:" in body[:20]:
        body = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")][-1]
    return json.loads(body), sid
r, sid = call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "probe", "version": "1"}})
urllib.request.urlopen(urllib.request.Request(U, json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode(), dict(H, **{"Mcp-Session-Id": sid})), timeout=30) if sid else None
for name, args in [("get_champion", {}), ("list_miner_task_batches", {"limit": 5})]:
    r, sid = call("tools/call", {"name": name, "arguments": args}, sid, 2)
    c = r.get("result", {}).get("content", [{}])[0].get("text", json.dumps(r)[:1500])
    print("==", name); print(c[:2500])
