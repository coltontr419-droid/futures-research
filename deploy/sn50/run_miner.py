"""Start the stock Synth (SN50) miner with our forecasts (decisions.md §1189). Replaces only synth.miner.simulations.generate_simulations, which
neurons/miner.py imports by name, with futuresres.synth.miner_model.generate_simulations (same signature). Same arguments as neurons/miner.py."""

import runpy
import sys

sys.path.insert(0, "/opt/synth/ours/src")
sys.path.insert(0, "/opt/synth/repo")

import synth.miner.simulations as stock  # noqa: E402
from futuresres.synth.miner_model import generate_simulations  # noqa: E402

stock.generate_simulations = generate_simulations
runpy.run_path("/opt/synth/repo/neurons/miner.py", run_name="__main__")
