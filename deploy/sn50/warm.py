"""Keep the Synth forecaster caches warm (decisions.md §1221): one forecast per asset and horizon every 15 min, so live requests never pay the cold
fetch (≈ 6-7 s per asset)."""
import datetime as dt
from futuresres.synth.miner_model import generate_simulations
start = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1)).replace(second=0, microsecond=0).isoformat()
for a in ("BTC", "ETH", "SOL", "XRP", "HYPE"): generate_simulations(a, start, 60, 3600, 10)
for a in ("BTC", "ETH", "SOL", "XRP", "HYPE", "XAU", "SP500", "NVDAX", "TSLAX", "AAPLX", "GOOGLX", "WTIOIL", "SPCX"): generate_simulations(a, start, 300, 86400, 10)
