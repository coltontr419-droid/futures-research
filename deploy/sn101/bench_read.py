"""Hourly bench read (§1211 add. 13): UID 210's aggregate 24 h mean gap to the median at the largest SN101 validator, appended to bench_reads.txt."""
import numpy as np, bittensor as bt, time
st = bt.Subtensor(network="finney"); m = st.metagraph(101, lite=True); S = np.array(m.S); vp = np.array(m.validator_permit)
val = int(max([v for v in range(len(S)) if vp[v]], key=lambda v: S[v])); blk = st.get_current_block()
w = st.query_subtensor("Weights", block=blk, params=[101, val]); arr = np.zeros(256)
for u, x in (w.value if hasattr(w, "value") else w): arr[int(u)] = float(x)
pos = arr[arr > 0]; g = np.log(arr[210] / np.median(pos)) / 10 if arr[210] > 0 else float("nan")
open("/opt/tag101/bench_reads.txt", "a").write(f"{time.strftime('%Y-%m-%dT%H:%M', time.gmtime())} block {blk} gap {g:+.5f}\n")
