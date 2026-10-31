"""Hone (SN5) cost / pass-rate trial (decisions.md §1198): run the reference demo miner's own agent loop (DemoMiner._generate, read-only
workspace tools, 48-call budget, ≈ 260 s of model time as live) on a retired fixture through an OpenAI-compatible endpoint (OpenRouter),
then grade the answer in the pinned sandbox (scripts/try_task.py grade, as an unprivileged user). Records tokens, cost, tool calls, time.

    sudo -u hone /opt/hone/venv/bin/python hone_trial.py <fixture dir> <model> <attempts> <results.jsonl>
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, "/opt/hone/repo")
from rlvr.neurons.demo_miner import BedrockClient, DemoMiner  # noqa: E402
from rlvr.v3.miner_workspace import WorkspaceReader  # noqa: E402

PRICES = {  # $ per million tokens (OpenRouter, 2026-10-31)
    "moonshotai/kimi-k3": (0.19, 15.00), "deepseek/deepseek-v4.1-flash": (0.04, 0.50), "z-ai/glm-5.3-flash": (0.02, 0.15),
    "z-ai/glm-5.3": (0.07, 1.40),
}
MODEL_SECONDS = 260.0


def key() -> str:
    for line in open("/opt/hone/openrouter.env"):
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no key")


async def attempt(fixture: Path, workspace: Path, model: str) -> dict:
    ident = json.loads((fixture / "identity.json").read_text())
    identity = SimpleNamespace(**ident)
    request = SimpleNamespace(identity=identity, workspace=SimpleNamespace(sha256=ident.get("workspace_sha256", "")))
    settings = SimpleNamespace(bedrock_api_key=key(), bedrock_base_url="https://openrouter.ai/api/v1", bedrock_model=model,
                               bedrock_max_tokens=16_384, bedrock_temperature=1.0, bedrock_reasoning_effort="high",
                               bedrock_request_timeout_s=280.0, bedrock_max_retries=2, miner_max_workspace_tool_calls=48)
    miner = DemoMiner.__new__(DemoMiner)
    miner.settings = settings
    miner.client = BedrockClient(settings)
    usage = {"in": 0, "out": 0, "calls": 0}
    orig = miner.client.complete

    async def counted(*a, **k):
        c = await orig(*a, **k)
        u = json.loads(c.response_body).get("usage") or {}
        usage["in"] += u.get("prompt_tokens", 0); usage["out"] += u.get("completion_tokens", 0); usage["calls"] += 1
        return c
    miner.client.complete = counted
    t0 = time.monotonic(); err = None; patch = b""
    try:
        _, events, patch = await miner._generate(request, WorkspaceReader(workspace), time.monotonic() + MODEL_SECONDS)
        tools = sum(1 for e in events if e.get("event_type") == "tool_call")
    except Exception as e:  # timeouts, budget exhausted, provider errors: a fail, as live
        err, tools = f"{type(e).__name__}: {e}"[:200], None
    finally:
        await miner.client.aclose()
    pin, pout = PRICES.get(model, (0.0, 0.0))
    out = {"model": model, "fixture": fixture.name, "seconds": round(time.monotonic() - t0, 1), "model_calls": usage["calls"], "tool_calls": tools,
           "tokens_in": usage["in"], "tokens_out": usage["out"], "cost_usd": round(usage["in"] * pin / 1e6 + usage["out"] * pout / 1e6, 4), "error": err}
    if patch and not err:
        with tempfile.NamedTemporaryFile("wb", suffix=".ans", delete=False, dir="/opt/hone/work") as f:
            f.write(patch); ans = f.name
        g = subprocess.run([sys.executable, "scripts/try_task.py", "--fixture", str(fixture), "grade", ans], cwd="/opt/hone/repo",
                           capture_output=True, text=True, timeout=900)
        lines = (g.stdout + g.stderr).splitlines()
        out["status"] = next((l.split(":", 1)[1].strip() for l in lines if l.startswith("status:")), "ungraded")
        out["checks_passed"] = sum(1 for l in lines if l.strip().endswith(": passed") and not l.startswith("status"))
        os.unlink(ans)
    else:
        out["status"] = "no answer"
    return out


def main() -> None:
    fixture, model, n, results = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4]
    workspace = Path("/opt/hone/work") / (fixture.name + "-ws")
    if not workspace.exists():
        subprocess.run([sys.executable, "scripts/try_task.py", "--fixture", str(fixture), "extract", str(workspace)], cwd="/opt/hone/repo",
                       check=True, capture_output=True)
    for _ in range(n):
        r = asyncio.run(attempt(fixture, workspace, model))
        print(json.dumps(r), flush=True)
        with open(results, "a") as f:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
