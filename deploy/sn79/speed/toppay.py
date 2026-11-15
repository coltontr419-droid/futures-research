import json, urllib.request, bittensor as bt, numpy as np
try: tao = json.load(urllib.request.urlopen("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", timeout=20))["bittensor"]["usd"]
except Exception: tao = float("nan")
st = bt.Subtensor(network="finney"); m = st.metagraph(79, lite=True); blk = st.get_current_block()
tempo = st.query_subtensor("Tempo", params=[79]).value; alpha = float(st.subnet(79).price)
E = np.array(m.emission, dtype=float); usd = E * (7200 / (tempo + 1)) * alpha * tao * 30
json.dump({int(i): float(usd[i]) for i in range(256)}, open("/opt/mvtrx/speed/pay_all.json", "w"))
top = np.argsort(-usd)[:30]
print(",".join(str(int(i)) for i in top))
print(" ".join(f"{int(i)}:${usd[i]:.0f}" for i in top))
