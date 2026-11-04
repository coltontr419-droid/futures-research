"""Every Synth prompt type through Synth's own validate_responses (decisions.md §1221)."""
import datetime as dt, time
from synth.simulation_input import SimulationInput
from synth.validator.response_validation_v2 import validate_responses
from futuresres.synth.miner_model import generate_simulations
start = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)).replace(second=0, microsecond=0).isoformat()
cases = [(a, 60, 3600) for a in ("BTC", "ETH", "SOL", "XRP", "HYPE")] + [(a, 300, 86400) for a in ("BTC", "ETH", "SOL", "XRP", "HYPE", "XAU", "SP500", "NVDAX", "TSLAX", "AAPLX", "GOOGLX", "WTIOIL", "SPCX")]
bad = 0
for a, ti, tl in cases:
    t = time.time()
    try:
        p = generate_simulations(a, start, ti, tl, 1000)
        si = SimulationInput(asset=a, start_time=start, time_increment=ti, time_length=tl, num_simulations=1000)
        res = validate_responses(p, si, f"{time.time() - t:.2f}")
    except Exception as e:
        res = f"ERROR {type(e).__name__}: {str(e)[:80]}"
    bad += res != "CORRECT"
    print(f"{a:6} {ti:3d}s / {tl:5d}s: {res} ({time.time() - t:.1f}s)", flush=True)
print("all CORRECT" if not bad else f"{bad} failed")
