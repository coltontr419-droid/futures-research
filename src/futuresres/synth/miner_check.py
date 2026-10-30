"""Check our SN50 forecasts with the subnet's own response validator (synth/validator/response_validation_v2.py) for every asset and prompt type,
timing each call. decisions.md §1177. Needs the synth-subnet repo at ~/sn50/synth-subnet.

    python -m futuresres.synth.miner_check
"""

from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / "sn50" / "synth-subnet"))

from synth.simulation_input import SimulationInput  # noqa: E402
from synth.validator.response_validation_v2 import validate_responses  # noqa: E402

from futuresres.synth.miner_model import generate_simulations  # noqa: E402

LF = ["BTC", "ETH", "SOL", "XRP", "HYPE", "XAU", "SP500", "NVDAX", "GOOGLX", "TSLAX", "AAPLX", "WTIOIL", "SPCX"]
HF = ["BTC", "ETH", "SOL", "XRP", "HYPE"]


def main() -> int:
    start = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1)).replace(second=0, microsecond=0).isoformat()
    bad = 0
    for assets, inc, length in ((LF, 300, 86400), (HF, 60, 3600)):
        for a in assets:
            si = SimulationInput(asset=a, start_time=start, time_increment=inc, time_length=length, num_simulations=1000)
            t = time.time()
            try:
                out = generate_simulations(a, start, inc, length, 1000)
                verdict = validate_responses(out, si, f"{time.time() - t:.2f}")
            except Exception as e:
                verdict = f"EXCEPTION {type(e).__name__}: {e}"
            took = time.time() - t; bad += verdict != "CORRECT"
            print(f"{a:7} {inc:4}s/{length // 3600:2}h  {verdict[:90]:30}  {took:5.1f}s", flush=True)
    print("all correct" if not bad else f"{bad} problems")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
