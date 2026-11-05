"""Hone's demo agent loop on SWE-bench Verified tasks (decisions.md §1226): same client settings as hone_trial.py trial 5
(OpenRouter fastest host, logprobs off, 32k replies, 6 correction rounds, 260 s of model time). Writes SWE-bench predictions + cost rows.
    sudo -u hone /opt/hone/venv/bin/python swe_agent.py <model> <preds.jsonl> <results.jsonl>"""
import asyncio, json, os, sys, time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, "/opt/hone/repo"); sys.path.insert(0, "/opt/hone")
os.environ.setdefault("PROVIDER", "openrouter"); os.environ.setdefault("REASKS", "6"); os.environ.setdefault("MAXTOK", "32768")
import hone_trial as ht                                   # key(), BASE, the reask limit patch
from rlvr.neurons.demo_miner import BedrockClient, DemoMiner
from rlvr.v3.miner_workspace import WorkspaceReader
import httpx


class _Strip(httpx.AsyncClient):
    async def post(self, url, *a, content=None, **kw):
        if content:
            d = json.loads(content); d.pop("top_logprobs", None); d["logprobs"] = False
            d["provider"] = {"sort": "throughput"}; d["usage"] = {"include": True}; content = json.dumps(d).encode()
        return await super().post(url, *a, content=content, **kw)


async def solve(task, model):
    identity = SimpleNamespace(task_type="repository_patch_v1", instruction=task["problem_statement"], working_directory=".")
    request = SimpleNamespace(identity=identity, workspace=SimpleNamespace(sha256=""))
    settings = SimpleNamespace(bedrock_api_key=ht.key(), bedrock_base_url=ht.BASE, bedrock_model=model, bedrock_max_tokens=int(os.environ["MAXTOK"]),
                               bedrock_temperature=1.0, bedrock_reasoning_effort=os.getenv("EFFORT", "medium"), bedrock_request_timeout_s=280.0,
                               bedrock_max_retries=2, miner_max_workspace_tool_calls=48)
    miner = DemoMiner.__new__(DemoMiner); miner.settings = settings
    miner.client = BedrockClient(settings, http=_Strip(headers={"User-Agent": "hone-test/1.0"}, timeout=120))
    use = {"in": 0, "out": 0, "calls": 0, "cost": 0.0}; orig = miner.client.complete

    async def counted(*a, **k):
        c = await orig(*a, **k); u = json.loads(c.response_body).get("usage") or {}
        use["in"] += u.get("prompt_tokens", 0); use["out"] += u.get("completion_tokens", 0); use["calls"] += 1; use["cost"] += float(u.get("cost") or 0)
        return c
    miner.client.complete = counted
    t0 = time.monotonic(); err = None; patch = b""
    try:
        _, _, patch = await miner._generate(request, WorkspaceReader(Path("/opt/swe/ws") / task["instance_id"]), time.monotonic() + 260.0)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"[:200]
    finally:
        await miner.client.aclose()
    return patch.decode("utf-8", "replace"), {"instance_id": task["instance_id"], "model": model, "seconds": round(time.monotonic() - t0, 1),
                                              "calls": use["calls"], "tokens_in": use["in"], "tokens_out": use["out"], "cost_usd": round(use["cost"], 4), "error": err}


def main():
    model, preds, results = sys.argv[1], sys.argv[2], sys.argv[3]
    done = {json.loads(l)["instance_id"] for l in open(results)} if os.path.exists(results) else set()
    for t in json.load(open("/opt/swe/tasks.json")):
        if t["instance_id"] in done: continue
        patch, row = asyncio.run(solve(t, model))
        with open(preds, "a") as f: f.write(json.dumps({"instance_id": t["instance_id"], "model_name_or_path": model, "model_patch": patch}) + "\n")
        with open(results, "a") as f: f.write(json.dumps(row) + "\n")
        print(json.dumps(row), flush=True)


main()
